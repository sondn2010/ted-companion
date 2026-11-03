"""Module lấy thông tin cửa sổ active (Foreground Window) trên hệ điều hành.

Hỗ trợ:
- Windows (qua ctypes Win32 API GetForegroundWindow + QueryFullProcessImageNameW)
- Khả năng thay thế backend giả lập (mocking) phục vụ 100% test tự động độc lập với môi trường chạy.
"""

from dataclasses import dataclass
import logging
import os
import sys
from typing import Callable, Optional

logger = logging.getLogger("ted")


@dataclass
class ActiveWindowInfo:
    title: str
    process_name: str
    hwnd: int = 0
    pid: int = 0


def _clean_window_title(raw_title: str) -> str:
    """Loại bỏ ký tự lạ và cắt ngắn tiêu đề để an toàn về bộ nhớ & riêng tư."""
    if not raw_title:
        return ""
    # Giới hạn 200 ký tự
    title = raw_title.strip()[:200]
    return title


def _windows_native_inspector() -> Optional[ActiveWindowInfo]:
    """Lấy tiêu đề và tên process của cửa sổ active trên Windows bằng ctypes."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        # 1. Lấy Window Title (UTF-16)
        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value

        # 2. Lấy PID
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return ActiveWindowInfo(title=_clean_window_title(title), process_name="", hwnd=hwnd, pid=0)

        # 3. Lấy tên file thực thi (Process Name)
        process_name = ""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h_process:
            try:
                exe_buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(h_process, 0, exe_buf, ctypes.byref(size)):
                    process_name = os.path.basename(exe_buf.value)
            finally:
                kernel32.CloseHandle(h_process)

        return ActiveWindowInfo(
            title=_clean_window_title(title),
            process_name=process_name.lower(),
            hwnd=hwnd,
            pid=pid.value
        )
    except Exception as exc:
        logger.debug("Không đọc được cửa sổ active: %s", exc)
        return None


class WindowInspector:
    """Inspector có thể cấu hình backend linh hoạt."""

    def __init__(self, backend_fn: Optional[Callable[[], Optional[ActiveWindowInfo]]] = None):
        if backend_fn is not None:
            self._backend = backend_fn
        elif sys.platform == "win32":
            self._backend = _windows_native_inspector
        else:
            self._backend = lambda: None

    def get_active_window(self) -> Optional[ActiveWindowInfo]:
        """Trả về thông tin cửa sổ active hiện tại hoặc None."""
        try:
            return self._backend()
        except Exception as e:
            logger.debug("Lỗi khi gọi backend window inspector: %s", e)
            return None
