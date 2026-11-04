"""Quick chat: không gửi chồng khi đang stream, escape HTML, nhãn hiển thị thay prefill giao thức."""

import asyncio
from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal
from qt_offscreen_app_helper import get_qapp

from src.core.background_task_spawner import _running_tasks
from src.ui.quick_chat_popup import QuickChatPopup


class _Focus(QObject):
    character_changed = Signal(str)
    current_mood = "IDLE"

    def get_context_snapshot(self):
        return {}

    def set_mood(self, mood):
        pass

    def record_distraction(self, parked_idea_text=None):
        pass


def _popup(stream):
    get_qapp()
    client = SimpleNamespace(connection=SimpleNamespace(name="T"), stream_chat=stream)
    pool = SimpleNamespace(for_module=lambda _m: client)
    return QuickChatPopup(_Focus(), pool, SimpleNamespace(active=lambda: None))


async def test_enter_during_stream_does_not_start_second_request():
    gate, calls = asyncio.Event(), []

    async def stream(user_message, current_context, on_mood_change, on_token, **_kw):
        calls.append(user_message)
        await gate.wait()
        return ""

    popup = _popup(stream)
    popup.input_chat.setText("câu 1")
    popup.input_chat.returnPressed.emit()
    popup.input_chat.setText("câu 2")
    popup.input_chat.returnPressed.emit()          # Enter không đi qua nút Gửi đã disable
    await asyncio.sleep(0)
    assert calls == ["câu 1"]
    gate.set()
    await asyncio.gather(*list(_running_tasks))
    popup.input_chat.setText("câu 3")
    popup.input_chat.returnPressed.emit()
    await asyncio.gather(*list(_running_tasks))
    assert calls == ["câu 1", "câu 3"]


async def test_user_text_is_html_escaped_and_display_text_replaces_protocol_prefill():
    async def stream(user_message, current_context, on_mood_change, on_token, **_kw):
        return ""

    popup = _popup(stream)
    popup.input_chat.setText("<b>đậm</b>")
    popup.input_chat.returnPressed.emit()
    await asyncio.gather(*list(_running_tasks))
    assert "<b>đậm</b>" in popup.chat_view.toPlainText()          # hiện nguyên văn, không bị render
    popup.open_for("thcs", prefill="[TED_EXPLAIN_MISTAKE]\n<json>{}</json>", auto_send=True, display_text="Vì sao mình sai câu này?")
    await asyncio.gather(*list(_running_tasks))
    text = popup.chat_view.toPlainText()
    assert "Vì sao mình sai câu này?" in text and "TED_EXPLAIN_MISTAKE" not in text


def test_nudge_and_parked_idea_are_escaped():
    popup = _popup(None)
    popup.show_hermes_nudge("CHEER", "<i>x</i>")
    popup.input_parking.setText("<u>việc</u>")
    popup.input_parking.returnPressed.emit()
    text = popup.chat_view.toPlainText()
    assert "<i>x</i>" in text and "<u>việc</u>" in text
    popup.show_mindful_ping("<b>Bài</b>")
    assert "<b>Bài</b>" in popup.ping_banner.lbl_question.text().replace("&lt;", "<").replace("&gt;", ">")
