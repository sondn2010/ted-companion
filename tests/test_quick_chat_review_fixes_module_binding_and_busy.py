"""Regression review: M5 (ping/nudge gắn module work + transcript theo module), M6 (open_for khi đang stream)."""

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

    def record_distraction(self, **_k):
        pass


def _popup():
    get_qapp()
    pool = SimpleNamespace(for_module=lambda m: SimpleNamespace(connection=SimpleNamespace(name=f"conn-{m}")))
    return QuickChatPopup(_Focus(), pool, SimpleNamespace(active=lambda: None, get=lambda _m: None))


def test_mindful_ping_and_nudge_rebind_to_work():
    popup = _popup()
    popup.open_for("thcs")
    assert popup._current_module_id() == "thcs"
    popup.show_mindful_ping("Báo cáo")
    assert popup._current_module_id() == "work" and "conn-work" in popup.lbl_mode_badge.text()
    popup.open_for("thcs")
    popup.show_hermes_nudge("CHEER", "ok")   # nhắc chỉ lưu vào hội thoại work, không giật trang đang xem
    assert popup._current_module_id() == "thcs"


def test_transcripts_are_partitioned_per_module():
    popup = _popup()
    popup.open_for("thcs")
    popup._log_html("<p>BÀI-CỦA-CON</p>")
    popup.show_hermes_nudge("CHEER", "VIỆC-CỦA-BỐ")
    assert "VIỆC-CỦA-BỐ" not in popup.chat_view.toPlainText()
    popup.open_for("work")
    text = popup.chat_view.toPlainText()
    assert "VIỆC-CỦA-BỐ" in text and "BÀI-CỦA-CON" not in text
    popup.open_for("thcs")
    text = popup.chat_view.toPlainText()
    assert "BÀI-CỦA-CON" in text and "VIỆC-CỦA-BỐ" not in text


def test_stream_into_hidden_module_is_replayed_when_returning():
    popup = _popup()
    popup.open_for("thcs")
    popup.transcripts.append_html("thcs", "<p>Ted: ")
    popup.open_for("work")
    popup.transcripts.insert_text("thcs", "trả lời dở")
    assert "trả lời dở" not in popup.chat_view.toPlainText()
    popup.open_for("thcs")
    assert "trả lời dở" in popup.chat_view.toPlainText()


def test_open_for_auto_send_refused_while_streaming():
    popup = _popup()
    popup._in_flight = True
    popup._display_override = "nhãn cũ"
    assert popup.open_for("thcs", prefill="[TED_QUIZ]\n<json>{}</json>", auto_send=True, display_text="Giải thích") is False
    assert popup.input_chat.text() == "" and popup._display_override is None
    assert "Ted đang trả lời, thử lại sau nhé" in popup.chat_view.toPlainText()


def test_open_for_manual_prefill_and_plain_open_return_true():
    popup = _popup()
    assert popup.open_for("thcs") is True
    popup._in_flight = True
    assert popup.open_for("thcs", prefill="gợi ý") is True and popup.input_chat.text() == "gợi ý"


async def test_open_for_auto_send_returns_true_when_sent(monkeypatch):
    popup = _popup()
    monkeypatch.setattr("src.ui.quick_chat_popup.spawn_background_task", lambda coro, _n: coro.close())
    assert popup.open_for("thcs", prefill="xin chào", auto_send=True, display_text="Chào") is True
    assert popup._in_flight is True and "Chào" in popup.chat_view.toPlainText()
