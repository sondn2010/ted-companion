"""Backend Windows: user32.RegisterHotKey(NULL, id, mods, vk) → WM_HOTKEY vào hàng đợi luồng chính → Qt native event filter.

Không dùng hook bàn phím mức thấp (SetWindowsHookEx): chỉ nhận đúng các tổ hợp đã đăng ký, không ghi phím.
"""

import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, QTimer, Signal

from src.core.hotkeys.qt_key_sequence_to_win32_modifiers_vk import to_win32_modifiers_vk

logger = logging.getLogger("ted")

WM_HOTKEY = 0x0312
ERROR_HOTKEY_ALREADY_REGISTERED = 1409


class _HotkeyMessageFilter(QAbstractNativeEventFilter):
    """Bắt WM_HOTKEY từ vòng lặp sự kiện Qt (qasync dùng chính dispatcher của Qt nên filter vẫn chạy)."""

    def __init__(self, on_hotkey):
        super().__init__()
        self._on_hotkey = on_hotkey

    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    self._on_hotkey(int(msg.wParam))
                    return True, 0
        except Exception:   # không bao giờ để lỗi trong filter làm sập vòng lặp sự kiện
            logger.exception("Lỗi xử lý WM_HOTKEY")
        return False, 0


class WindowsRegisterHotKeyBackend(QObject):
    is_global = True
    activated = Signal(int)

    def __init__(self):
        super().__init__()
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)   # lỗi ở đây → manager rơi về QShortcut
        self._user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self._user32.RegisterHotKey.restype = wintypes.BOOL
        self._user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.UnregisterHotKey.restype = wintypes.BOOL
        self._ids: set[int] = set()
        self._filter = _HotkeyMessageFilter(self._dispatch)   # giữ tham chiếu mạnh
        app = QCoreApplication.instance()
        if app is None:
            raise RuntimeError("Cần QCoreApplication trước khi đăng ký phím tắt toàn cục")
        app.installNativeEventFilter(self._filter)

    def _dispatch(self, hotkey_id: int) -> None:
        if hotkey_id in self._ids:
            QTimer.singleShot(0, lambda: self.activated.emit(hotkey_id))   # không chạy UI trong khung filter

    def register(self, hotkey_id: int, seq: str) -> tuple[bool, str]:
        mapped = to_win32_modifiers_vk(seq)
        if mapped is None:
            return False, "unsupported_key"
        try:
            if self._user32.RegisterHotKey(None, hotkey_id, mapped[0], mapped[1]):
                self._ids.add(hotkey_id)
                return True, ""
            err = ctypes.get_last_error()
        except Exception as exc:
            logger.warning("RegisterHotKey lỗi: %s", exc)
            return False, "error"
        return False, "os_taken" if err == ERROR_HOTKEY_ALREADY_REGISTERED else "error"

    def unregister(self, hotkey_id: int) -> None:
        if hotkey_id not in self._ids:
            return
        self._ids.discard(hotkey_id)
        try:
            self._user32.UnregisterHotKey(None, hotkey_id)
        except Exception as exc:
            logger.warning("UnregisterHotKey lỗi: %s", exc)
