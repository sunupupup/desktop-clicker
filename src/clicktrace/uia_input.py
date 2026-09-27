from __future__ import annotations

import os
import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path


class UIAutomationClicker:
    """Invoke accessible desktop controls by screen point without moving the cursor."""

    TIMEOUT_SECONDS = 2.0

    def __init__(self, own_process_id: int | None = None) -> None:
        self._requests: queue.Queue[tuple[int, int, Callable[[str], None]] | None] = queue.Queue()
        self._state_lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._active_since: float | None = None
        self._closed = False
        self._own_process_id = own_process_id if own_process_id is not None else os.getpid()
        self._powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        self._worker = threading.Thread(target=self._run, name="uia-click-worker", daemon=True)
        self._watchdog = threading.Thread(target=self._watch, name="uia-click-watchdog", daemon=True)
        self._worker.start()
        self._watchdog.start()

    def request(self, x: int, y: int, callback: Callable[[str], None]) -> None:
        if self._closed:
            callback("ERROR")
            return
        self._requests.put((x, y, callback))

    def _start_process(self) -> subprocess.Popen[str] | None:
        if self._powershell is None:
            return None
        script = Path(__file__).with_name("uia_worker.ps1")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            return subprocess.Popen(
                [
                    self._powershell,
                    "-NoProfile",
                    "-STA",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    str(self._own_process_id),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
                creationflags=creationflags,
            )
        except OSError:
            return None

    def _run(self) -> None:
        while True:
            request = self._requests.get()
            if request is None:
                return
            x, y, callback = request
            if self._closed:
                self._safe_callback(callback, "ERROR")
                continue
            process = self._process
            if process is None or process.poll() is not None:
                process = self._start_process()
                self._process = process
            if process is None or process.stdin is None or process.stdout is None:
                self._safe_callback(callback, "ERROR")
                continue

            with self._state_lock:
                self._active_since = time.monotonic()
            try:
                process.stdin.write(f"{x}\t{y}\n")
                process.stdin.flush()
                result = process.stdout.readline().strip()
                if result not in {"INVOKED", "TOGGLED", "SELECTED", "NO_PATTERN", "SELF"}:
                    result = "TIMEOUT" if process.poll() is not None else "ERROR"
            except (OSError, ValueError):
                result = "TIMEOUT" if process.poll() is not None else "ERROR"
            finally:
                with self._state_lock:
                    self._active_since = None
            self._safe_callback(callback, result)

    def _watch(self) -> None:
        while not self._closed:
            time.sleep(0.1)
            with self._state_lock:
                active_since = self._active_since
                process = self._process
            if active_since is not None and time.monotonic() - active_since > self.TIMEOUT_SECONDS:
                if process is not None and process.poll() is None:
                    process.kill()

    @staticmethod
    def _safe_callback(callback: Callable[[str], None], result: str) -> None:
        try:
            callback(result)
        except Exception:
            pass

    def close(self) -> None:
        self._closed = True
        self._requests.put(None)
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
