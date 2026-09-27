from __future__ import annotations

import ctypes
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path


class _Point(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class _Rect(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def _android_coordinates(hwnd: int, x: int, y: int, display_width: int, display_height: int) -> tuple[int, int]:
    """Map a desktop point into the centered, aspect-fit Android display in an emulator client area."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(_Rect)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(_Point)]
    user32.ClientToScreen.restype = wintypes.BOOL
    handle = wintypes.HWND(hwnd)
    client = _Rect()
    if not user32.GetClientRect(handle, ctypes.byref(client)):
        raise ctypes.WinError(ctypes.get_last_error())
    width = client.right - client.left
    height = client.bottom - client.top
    if width <= 0 or height <= 0 or display_width <= 0 or display_height <= 0:
        raise RuntimeError("无法读取模拟器显示区域尺寸。")

    origin = _Point(0, 0)
    if not user32.ClientToScreen(handle, ctypes.byref(origin)):
        raise ctypes.WinError(ctypes.get_last_error())
    local_x, local_y = x - origin.x, y - origin.y
    scale = min(width / display_width, height / display_height)
    viewport_width = display_width * scale
    viewport_height = display_height * scale
    offset_x = (width - viewport_width) / 2
    offset_y = (height - viewport_height) / 2
    if not (
        offset_x <= local_x < offset_x + viewport_width
        and offset_y <= local_y < offset_y + viewport_height
    ):
        raise RuntimeError("点击坐标不在模拟器显示画面内（可能落在黑边或工具栏）。")

    android_x = int((local_x - offset_x) * display_width / viewport_width)
    android_y = int((local_y - offset_y) * display_height / viewport_height)
    return min(max(android_x, 0), display_width - 1), min(max(android_y, 0), display_height - 1)


class AndroidTouchClicker:
    """Inject touchscreen taps into a MuMu Android guest without desktop mouse input."""

    TIMEOUT_SECONDS = 4.0
    SERIAL_CACHE_SECONDS = 30.0
    DISPLAY_CACHE_SECONDS = 5.0

    def __init__(self) -> None:
        self._requests: queue.Queue[tuple[int, int, int, int, Callable[[str], None]] | None] = queue.Queue()
        self._closed = False
        self._serial_cache: dict[int, tuple[float, str, str]] = {}
        self._display_cache: dict[str, tuple[float, int, int]] = {}
        self._worker = threading.Thread(target=self._run, name="android-touch-worker", daemon=True)
        self._worker.start()

    def request(self, hwnd: int, process_id: int, x: int, y: int, callback: Callable[[str], None]) -> None:
        if self._closed:
            callback("ERROR:模拟器触摸工作线程已关闭。")
            return
        self._requests.put((hwnd, process_id, x, y, callback))

    @staticmethod
    def _hidden_run(args: list[str], *, timeout: float = 4.0) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(f"启动模拟器命令失败：{error}") from error

    @staticmethod
    def _netstat_ports(process_id: int) -> list[int]:
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        netstat = shutil.which("netstat.exe") or str(Path(system_root) / "System32" / "netstat.exe")
        result = AndroidTouchClicker._hidden_run([netstat, "-ano", "-p", "tcp"], timeout=2.0)
        if result.returncode:
            raise RuntimeError(f"无法读取模拟器 ADB 端口：{result.stderr.strip() or result.returncode}")
        ports: set[int] = set()
        for line in result.stdout.splitlines():
            columns = line.split()
            if len(columns) < 5 or columns[0].upper() != "TCP":
                continue
            if columns[3].upper() != "LISTENING" or columns[4] != str(process_id):
                continue
            try:
                ports.add(int(columns[1].rsplit(":", 1)[1]))
            except (IndexError, ValueError):
                continue
        return sorted(port for port in ports if 5550 <= port <= 5600)

    @staticmethod
    def _online_devices(adb: str) -> set[str]:
        result = AndroidTouchClicker._hidden_run([adb, "devices", "-l"], timeout=5.0)
        if result.returncode:
            raise RuntimeError(f"读取 ADB 设备列表失败：{result.stderr.strip() or result.returncode}")
        devices: set[str] = set()
        for line in result.stdout.splitlines():
            columns = line.split()
            if len(columns) >= 2 and columns[1] == "device":
                devices.add(columns[0])
        return devices

    def _adb_device(self, process_id: int, executable_path: str) -> tuple[str, str]:
        cached = self._serial_cache.get(process_id)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1], cached[2]

        executable_dir = Path(executable_path).parent
        bundled_adb = executable_dir / "adb.exe"
        adb = str(bundled_adb) if bundled_adb.is_file() else shutil.which("adb.exe")
        if adb is None:
            raise RuntimeError("未找到 MuMu 自带的 adb.exe。")

        ports = self._netstat_ports(process_id)
        if not ports:
            raise RuntimeError("没有找到此 MuMu 实例对应的 ADB 端口。")
        online = self._online_devices(adb)
        for port in ports:
            emulator_serial = f"emulator-{port - 1}"
            tcp_serial = f"127.0.0.1:{port}"
            if emulator_serial in online:
                serial = emulator_serial
            elif tcp_serial in online:
                serial = tcp_serial
            else:
                # MuMu can expose a separate ADB endpoint for each instance while
                # only one endpoint is connected to the shared ADB server. Connect
                # only to the loopback port owned by this exact MuMu device process.
                connected = self._hidden_run([adb, "connect", tcp_serial], timeout=5.0)
                online = self._online_devices(adb)
                if emulator_serial in online:
                    serial = emulator_serial
                elif tcp_serial in online:
                    serial = tcp_serial
                else:
                    detail = connected.stderr.strip() or connected.stdout.strip()
                    if detail:
                        raise RuntimeError(
                            f"无法连接此 MuMu 实例的 ADB 端口 {tcp_serial}：{detail}；未发送点击。"
                        )
                    continue
            self._serial_cache[process_id] = (
                time.monotonic() + self.SERIAL_CACHE_SECONDS,
                adb,
                serial,
            )
            return adb, serial
        raise RuntimeError("此 MuMu 实例的 ADB 端口未连接或处于离线状态；未发送点击。")

    def _display_size(self, adb: str, serial: str) -> tuple[int, int]:
        cached = self._display_cache.get(serial)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1], cached[2]
        result = self._hidden_run(
            [adb, "-s", serial, "shell", "dumpsys", "window", "displays"], timeout=3.0
        )
        if result.returncode:
            raise RuntimeError(f"读取 Android 显示尺寸失败：{result.stderr.strip() or result.returncode}")
        match = re.search(r"\bcur\s*=\s*(\d+)x(\d+)\b", result.stdout)
        if match is None:
            raise RuntimeError("无法读取 Android 当前旋转后的显示尺寸；未发送点击。")
        width, height = int(match.group(1)), int(match.group(2))
        self._display_cache[serial] = (time.monotonic() + self.DISPLAY_CACHE_SECONDS, width, height)
        return width, height

    def _send_tap(self, hwnd: int, process_id: int, x: int, y: int) -> None:
        executable_path = self._process_image_path(process_id)
        if Path(executable_path).name.casefold() != "mumunxdevice.exe":
            raise RuntimeError("目标窗口不是已支持的 MuMu Android 实例；未发送点击。")
        adb, serial = self._adb_device(process_id, executable_path)
        display_width, display_height = self._display_size(adb, serial)
        android_x, android_y = _android_coordinates(hwnd, x, y, display_width, display_height)
        result = self._hidden_run(
            [adb, "-s", serial, "shell", "input", "tap", str(android_x), str(android_y)],
            timeout=self.TIMEOUT_SECONDS,
        )
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip() or str(result.returncode)
            raise RuntimeError(f"MuMu ADB 触摸注入失败：{detail}")

    @staticmethod
    def _process_image_path(process_id: int) -> str:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        process = open_process(0x1000, False, process_id)
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            query_path = kernel32.QueryFullProcessImageNameW
            query_path.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
            query_path.restype = wintypes.BOOL
            path = ctypes.create_unicode_buffer(32_768)
            length = wintypes.DWORD(len(path))
            if not query_path(process, 0, path, ctypes.byref(length)):
                raise ctypes.WinError(ctypes.get_last_error())
            return path.value
        finally:
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            kernel32.CloseHandle(process)

    def _run(self) -> None:
        while True:
            request = self._requests.get()
            if request is None:
                return
            hwnd, process_id, x, y, callback = request
            try:
                self._send_tap(hwnd, process_id, x, y)
            except Exception as error:
                result = f"ERROR:{error}"
            else:
                result = "ANDROID_TAP"
            try:
                callback(result)
            except Exception:
                pass

    def close(self) -> None:
        self._closed = True
        self._requests.put(None)
