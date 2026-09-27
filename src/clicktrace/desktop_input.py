from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SM_CXSCREEN = 0
SM_CYSCREEN = 1
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
HWND_TOPMOST = ctypes.c_void_p(-1)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
GA_ROOT = 2


def _user32():
    if sys.platform != "win32":
        raise RuntimeError("桌面点击和浮层目前只支持 Windows。")
    return ctypes.WinDLL("user32", use_last_error=True)


def virtual_desktop_bounds() -> tuple[int, int, int, int]:
    """Return virtual desktop bounds as (left, top, width, height)."""
    get_system_metrics = _user32().GetSystemMetrics
    get_system_metrics.argtypes = [ctypes.c_int]
    get_system_metrics.restype = ctypes.c_int
    bounds = (
        get_system_metrics(SM_XVIRTUALSCREEN),
        get_system_metrics(SM_YVIRTUALSCREEN),
        get_system_metrics(SM_CXVIRTUALSCREEN),
        get_system_metrics(SM_CYVIRTUALSCREEN),
    )
    if bounds[2] < 2 or bounds[3] < 2:
        raise RuntimeError("无法读取 Windows 虚拟桌面尺寸。")
    return bounds


def primary_screen_bounds() -> tuple[int, int, int, int]:
    """Return the primary display bounds as (left, top, width, height)."""
    get_system_metrics = _user32().GetSystemMetrics
    get_system_metrics.argtypes = [ctypes.c_int]
    get_system_metrics.restype = ctypes.c_int
    width = get_system_metrics(SM_CXSCREEN)
    height = get_system_metrics(SM_CYSCREEN)
    if width < 2 or height < 2:
        raise RuntimeError("无法读取 Windows 主屏尺寸。")
    return 0, 0, width, height


def top_level_window(hwnd: int) -> int:
    """Return the native top-level HWND for a Tk widget/window handle."""
    get_ancestor = _user32().GetAncestor
    get_ancestor.argtypes = [wintypes.HWND, wintypes.UINT]
    get_ancestor.restype = wintypes.HWND
    root = get_ancestor(wintypes.HWND(hwnd), GA_ROOT)
    if not root:
        raise OSError("无法解析浮层的顶层 Windows 窗口句柄。")
    return int(root)


def set_overlay_click_through(hwnd: int, enabled: bool) -> None:
    user32 = _user32()
    get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    get_long.restype = ctypes.c_ssize_t
    set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    set_long.restype = ctypes.c_ssize_t
    handle = wintypes.HWND(hwnd)
    style = get_long(handle, GWL_EXSTYLE) | WS_EX_LAYERED
    style = style | WS_EX_TRANSPARENT if enabled else style & ~WS_EX_TRANSPARENT
    ctypes.set_last_error(0)
    previous = set_long(handle, GWL_EXSTYLE, style)
    if previous == 0 and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())

    set_pos = user32.SetWindowPos
    set_pos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    set_pos.restype = wintypes.BOOL
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
    if not set_pos(handle, None, 0, 0, 0, 0, flags):
        raise ctypes.WinError(ctypes.get_last_error())


def move_overlay(hwnd: int, x: int, y: int) -> None:
    set_pos = _user32().SetWindowPos
    set_pos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    set_pos.restype = wintypes.BOOL
    if not set_pos(
        wintypes.HWND(hwnd),
        HWND_TOPMOST,
        x,
        y,
        0,
        0,
        SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
    ):
        raise ctypes.WinError(ctypes.get_last_error())


class _Point(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def _pack_point(x: int, y: int) -> int:
    return ((y & 0xFFFF) << 16) | (x & 0xFFFF)


def window_process_id_at(x: int, y: int) -> int:
    """Return the process that owns the actual HWND under a screen coordinate."""
    return window_context_at(x, y)[0]


def window_process_info_at(x: int, y: int) -> tuple[int, str]:
    """Return the process ID and executable path under a physical screen point."""
    process_id, image_path, _hwnd = window_context_at(x, y)
    return process_id, image_path


def window_context_at(x: int, y: int) -> tuple[int, str, int]:
    """Return the process ID, image path, and HWND under a physical screen point."""
    user32 = _user32()
    window_from_point = user32.WindowFromPhysicalPoint
    window_from_point.argtypes = [_Point]
    window_from_point.restype = wintypes.HWND
    hwnd = window_from_point(_Point(x, y))
    if not hwnd:
        raise RuntimeError("点击坐标下没有可接收输入的窗口。")
    process_id = wintypes.DWORD()
    get_window_thread_process_id = user32.GetWindowThreadProcessId
    get_window_thread_process_id.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    get_window_thread_process_id.restype = wintypes.DWORD
    if not get_window_thread_process_id(hwnd, ctypes.byref(process_id)) or not process_id.value:
        raise OSError("无法读取点击目标窗口所属进程。")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    process = open_process(0x1000, False, process_id.value)  # PROCESS_QUERY_LIMITED_INFORMATION
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
        return int(process_id.value), path.value, int(hwnd)
    finally:
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle(process)


def post_left_click(
    x: int,
    y: int,
    *,
    excluded_hwnds: tuple[int, ...] = (),
) -> int:
    """Post a left-click message to the window at a desktop point without moving the cursor.

    Returns the target HWND. This queues Win32 window messages; it does not inject
    hardware-style mouse input and cannot guarantee that every application handles them.
    """
    user32 = _user32()
    window_from_point = user32.WindowFromPhysicalPoint
    window_from_point.argtypes = [_Point]
    window_from_point.restype = wintypes.HWND
    hwnd = window_from_point(_Point(x, y))
    target = int(hwnd or 0)
    if not target:
        raise RuntimeError("点击坐标下没有可接收输入的窗口。")
    is_child = user32.IsChild
    is_child.argtypes = [wintypes.HWND, wintypes.HWND]
    is_child.restype = wintypes.BOOL
    if any(
        target == excluded or is_child(wintypes.HWND(excluded), wintypes.HWND(target))
        for excluded in excluded_hwnds
    ):
        raise RuntimeError("点击坐标命中了连点器自身窗口，请将区域移到其他窗口上。")

    point = _Point(x, y)
    screen_to_client = user32.ScreenToClient
    screen_to_client.argtypes = [wintypes.HWND, ctypes.POINTER(_Point)]
    screen_to_client.restype = wintypes.BOOL
    if not screen_to_client(wintypes.HWND(target), ctypes.byref(point)):
        raise ctypes.WinError(ctypes.get_last_error())

    post_message = user32.PostMessageW
    post_message.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    ]
    post_message.restype = wintypes.BOOL
    coords = _pack_point(point.x, point.y)
    messages = (
        (WM_MOUSEMOVE, 0),
        (WM_LBUTTONDOWN, MK_LBUTTON),
        (WM_LBUTTONUP, 0),
    )
    button_down_posted = False
    for message, key_state in messages:
        if not post_message(wintypes.HWND(target), message, key_state, coords):
            error_code = ctypes.get_last_error()
            if button_down_posted:
                post_message(wintypes.HWND(target), WM_LBUTTONUP, 0, coords)
            raise ctypes.WinError(error_code)
        if message == WM_LBUTTONDOWN:
            button_down_posted = True
    return target
