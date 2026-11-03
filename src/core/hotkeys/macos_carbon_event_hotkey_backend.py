"""Backend macOS: Carbon RegisterEventHotKey + InstallEventHandler qua ctypes (không cần quyền Accessibility).

Callback Carbon chỉ phát tín hiệu qua QTimer.singleShot(0) – không chạy UI Python trong khung callback.
Lưu ý: chỉ phát hiện trùng với đăng ký Carbon khác (-9878); phím hệ thống (Spotlight…) mặc nhiên thắng.
"""

import ctypes
import logging

from PySide6.QtCore import QObject, QTimer, Signal

from src.core.hotkeys.qt_key_sequence_to_macos_carbon_keycode import fourcc, to_carbon_modifiers_keycode

logger = logging.getLogger("ted")

CARBON_PATH = "/System/Library/Frameworks/Carbon.framework/Carbon"
SIGNATURE = fourcc("TEDh")
K_EVENT_CLASS_KEYBOARD = fourcc("keyb")
K_EVENT_HOTKEY_PRESSED = 5
K_EVENT_PARAM_DIRECT_OBJECT = fourcc("----")
TYPE_EVENT_HOTKEY_ID = fourcc("hkid")
EVENT_HOTKEY_EXISTS_ERR = -9878


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class _EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


_HANDLER_PROC = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)


class MacCarbonEventHotKeyBackend(QObject):
    is_global = True
    activated = Signal(int)

    def __init__(self):
        super().__init__()
        c = ctypes.CDLL(CARBON_PATH)   # lỗi nạp → manager rơi về QShortcut
        c.GetApplicationEventTarget.restype = ctypes.c_void_p
        c.InstallEventHandler.argtypes = [ctypes.c_void_p, _HANDLER_PROC, ctypes.c_uint32,
                                          ctypes.POINTER(_EventTypeSpec), ctypes.c_void_p, ctypes.c_void_p]
        c.InstallEventHandler.restype = ctypes.c_int32
        c.RegisterEventHotKey.argtypes = [ctypes.c_uint32, ctypes.c_uint32, _EventHotKeyID,
                                          ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
        c.RegisterEventHotKey.restype = ctypes.c_int32
        c.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        c.UnregisterEventHotKey.restype = ctypes.c_int32
        c.GetEventParameter.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]
        c.GetEventParameter.restype = ctypes.c_int32
        self._carbon = c
        self._refs: dict[int, ctypes.c_void_p] = {}
        self._handler = _HANDLER_PROC(self._on_event)   # giữ tham chiếu mạnh, nếu không GC sẽ làm crash
        spec = _EventTypeSpec(K_EVENT_CLASS_KEYBOARD, K_EVENT_HOTKEY_PRESSED)
        status = c.InstallEventHandler(c.GetApplicationEventTarget(), self._handler, 1,
                                       ctypes.byref(spec), None, None)
        if status != 0:
            raise RuntimeError(f"InstallEventHandler thất bại: {status}")

    def _on_event(self, _next_handler, event, _user_data) -> int:
        try:
            hk = _EventHotKeyID()
            status = self._carbon.GetEventParameter(
                event, K_EVENT_PARAM_DIRECT_OBJECT, TYPE_EVENT_HOTKEY_ID, None,
                ctypes.sizeof(hk), None, ctypes.byref(hk))
            if status == 0 and hk.signature == SIGNATURE:
                hotkey_id = int(hk.id)
                QTimer.singleShot(0, lambda: self.activated.emit(hotkey_id))
        except Exception:
            logger.exception("Lỗi xử lý Carbon hotkey")
        return 0   # noErr

    def register(self, hotkey_id: int, seq: str) -> tuple[bool, str]:
        mapped = to_carbon_modifiers_keycode(seq)
        if mapped is None:
            return False, "unsupported_key"
        try:
            ref = ctypes.c_void_p()
            status = self._carbon.RegisterEventHotKey(
                mapped[1], mapped[0], _EventHotKeyID(SIGNATURE, hotkey_id), self._carbon.GetApplicationEventTarget(),
                0, ctypes.byref(ref))
        except Exception as exc:
            logger.warning("RegisterEventHotKey lỗi: %s", exc)
            return False, "error"
        if status == 0:
            self._refs[hotkey_id] = ref
            return True, ""
        return False, "os_taken" if status == EVENT_HOTKEY_EXISTS_ERR else "error"

    def unregister(self, hotkey_id: int) -> None:
        ref = self._refs.pop(hotkey_id, None)
        if ref is None:
            return
        try:
            self._carbon.UnregisterEventHotKey(ref)
        except Exception as exc:
            logger.warning("UnregisterEventHotKey lỗi: %s", exc)
