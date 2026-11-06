"""Module không có kết nối → khung chat báo rõ, không gọi mạng, nhả khoá gửi."""
from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal
from qt_offscreen_app_helper import get_qapp

from src.ui.quick_chat_popup import QuickChatPopup


class _Focus(QObject):
    character_changed = Signal(str)

    def get_context_snapshot(self):
        return {}

    def set_mood(self, _m):
        pass


async def test_send_with_missing_connection_shows_hint_and_unlocks():
    get_qapp()
    pool = SimpleNamespace(for_module=lambda _m: None)
    popup = QuickChatPopup(_Focus(), pool, SimpleNamespace(active=lambda: None, get=lambda _m: None))
    popup._in_flight = True
    await popup._stream_from_hermes("xin chào", None, "thcs")
    assert "Chưa cấu hình kết nối" in popup.chat_view.toPlainText()
    assert popup._in_flight is False and popup.btn_send.isEnabled()
