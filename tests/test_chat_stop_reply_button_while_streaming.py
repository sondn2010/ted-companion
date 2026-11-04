"""Đang stream câu trả lời: nút Chat/Gửi thành ⏹ Dừng, bấm là huỷ; ô nhập + Bãi đỗ vẫn dùng được."""
import asyncio
from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal
from qt_offscreen_app_helper import get_qapp

from src.ui.pet_speech_bubble_widget import PetSpeechBubble
from src.ui.quick_chat_popup import QuickChatPopup


class _Focus(QObject):
    character_changed = Signal(str)
    current_mood = "IDLE"

    def __init__(self):
        super().__init__()
        self.parked = []

    def get_context_snapshot(self):
        return {}

    def set_mood(self, _m):
        pass

    def record_distraction(self, parked_idea_text=None):
        self.parked.append(parked_idea_text)


class _SlowClient:
    """Phát 1 token rồi treo cho tới khi bị huỷ."""

    connection = SimpleNamespace(name="Fake")

    async def stream_chat(self, user_message, current_context, on_mood_change, on_token, persona, resume_mood=None):
        on_token("Đang trả lời")
        await asyncio.sleep(60)


async def _until(cond):
    for _ in range(100):
        if cond():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("điều kiện không đạt")


async def test_bubble_stop_cancels_reply_and_parking_still_works():
    get_qapp()
    focus = _Focus()
    pool = SimpleNamespace(for_module=lambda _m: _SlowClient())
    bubble = PetSpeechBubble(focus_engine=focus, client_pool=pool)
    bubble.open_chat(module_id="work")
    bubble._input_field.setText("gửi nhầm")
    bubble.btn_chat.click()
    await _until(lambda: "Đang trả lời" in bubble._chat_view.toPlainText())

    assert bubble._in_flight and bubble.btn_chat.isEnabled() and "Dừng" in bubble.btn_chat.text()
    bubble._input_field.setText("Ý tưởng chợt nhớ")
    bubble.btn_park.click()   # Bãi đỗ không bị khoá khi Ted đang trả lời
    assert focus.parked == ["Ý tưởng chợt nhớ"]

    bubble.btn_chat.click()   # ⏹ Dừng
    await _until(lambda: not bubble._in_flight)
    assert "Đã dừng" in bubble._chat_view.toPlainText()
    assert "Chat" in bubble.btn_chat.text() and bubble._stream_task is None


async def test_quick_chat_stop_cancels_reply_and_restores_send():
    get_qapp()
    pool = SimpleNamespace(for_module=lambda _m: _SlowClient())
    popup = QuickChatPopup(_Focus(), pool, SimpleNamespace(active=lambda: None, get=lambda _m: None))
    popup.input_chat.setText("gửi nhầm")
    popup.btn_send.click()
    await _until(lambda: "Đang trả lời" in popup.chat_view.toPlainText())

    assert popup._in_flight and popup.btn_send.isEnabled() and "Dừng" in popup.btn_send.text()
    popup.btn_send.click()   # ⏹ Dừng
    await _until(lambda: not popup._in_flight)
    assert "Đã dừng" in popup.chat_view.toPlainText()
    assert "Dừng" not in popup.btn_send.text() and popup._stream_task is None
