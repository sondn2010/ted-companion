"""Chọn/tạo backend phím tắt theo OS (import lười: chỉ nạp ctypes/Carbon khi cần) + đăng ký có dự phòng."""

import logging
import sys

logger = logging.getLogger("ted")


def default_native_backend():
    """Tạo backend toàn cục theo OS; None nếu OS không hỗ trợ."""
    if sys.platform == "win32":
        from src.core.hotkeys.windows_register_hotkey_backend import WindowsRegisterHotKeyBackend
        return WindowsRegisterHotKeyBackend()
    if sys.platform == "darwin":
        from src.core.hotkeys.macos_carbon_event_hotkey_backend import MacCarbonEventHotKeyBackend
        return MacCarbonEventHotKeyBackend()
    return None


def default_app_backend():
    from src.core.hotkeys.app_level_qshortcut_backend import AppLevelQShortcutBackend
    return AppLevelQShortcutBackend()


def create_backends(native_factory, app_factory) -> tuple:
    """(native, app): lỗi nạp backend toàn cục → native=None (manager rơi về QShortcut); không bao giờ ném lỗi."""
    native = app = None
    try:
        native = native_factory()
    except Exception:
        logger.exception("Không nạp được backend phím tắt toàn cục → dùng phím tắt trong app")
    try:
        app = app_factory()
    except Exception:
        logger.exception("Không tạo được backend QShortcut")
    return native, app


def register_with_fallback(native, app, int_id: int, seq: str, label: str) -> str:
    """Đăng ký 1 phím → "global" | "app_only" | "failed". Native bị OS chiếm vẫn đăng ký QShortcut để Ted có focus thì còn dùng được."""
    if native is not None:
        ok, reason = native.register(int_id, seq)
        if ok:
            return "global"
        logger.warning("Phím tắt %s (%s) không đăng ký được toàn cục: %s", label, seq, reason)
        if app is not None:
            app.register(int_id, seq)
        return "failed"
    return "app_only" if app is not None and app.register(int_id, seq)[0] else "failed"
