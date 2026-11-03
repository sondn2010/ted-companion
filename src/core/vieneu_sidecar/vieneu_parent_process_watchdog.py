"""Watchdog tiến trình cha cho sidecar VieNeu (chỉ stdlib): Ted bị kill cứng thì sidecar không được mồ côi."""

from __future__ import annotations

import os
import sys
import threading
import time


def is_process_alive(pid: int) -> bool:
    """Tiến trình `pid` còn sống? (chỉ stdlib). Dùng cho watchdog: Ted bị kill cứng thì sidecar không được mồ côi."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5   # ERROR_ACCESS_DENIED: còn sống nhưng không đủ quyền; lỗi khác = không tồn tại
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True   # không đọc được mã thoát: coi như còn sống (tránh tự tắt nhầm)
            return code.value == 259   # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)   # signal 0: chỉ kiểm tra tồn tại
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start_parent_watchdog(parent_pid: int, interval_s: float = 5.0, on_gone=None, alive=is_process_alive):
    """Luồng nền kiểm tra tiến trình cha mỗi `interval_s`; cha mất → gọi `on_gone` (mặc định thoát ngay)."""
    def _watch() -> None:
        while alive(parent_pid):
            time.sleep(interval_s)
        (on_gone or (lambda: os._exit(0)))()

    thread = threading.Thread(target=_watch, name="parent-watchdog", daemon=True)
    thread.start()
    return thread


