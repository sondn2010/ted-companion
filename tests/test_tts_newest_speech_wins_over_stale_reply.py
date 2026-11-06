"""Câu hỏi mới → chỉ đọc câu trả lời mới: câu cũ tổng hợp xong muộn hoặc đã bị stop() thì không được phát."""

import asyncio

import pytest

from src.config import settings
from src.core.tts_service import TTSService
from tests.qt_offscreen_app_helper import get_qapp


class _ControlledTTS(TTSService):
    """Tổng hợp giả: mỗi câu chờ một Event để test điều khiển thứ tự hoàn thành."""

    def __init__(self):
        super().__init__()
        self.gates: dict[str, asyncio.Event] = {}
        self.played: list[bytes] = []

    async def synthesize(self, text, lang=None, voice=None, **_kw):
        gate = self.gates.setdefault(text, asyncio.Event())
        await gate.wait()
        return text.encode()

    def _play_bytes(self, data: bytes) -> None:
        self.played.append(data)


@pytest.fixture
def tts(monkeypatch):
    get_qapp()
    monkeypatch.setattr(settings, "tts_enabled", True, raising=False)
    return _ControlledTTS()


@pytest.mark.asyncio
async def test_old_reply_finishing_after_new_one_is_not_played(tts):
    old = asyncio.create_task(tts.speak("Câu trả lời cũ rất dài."))
    await asyncio.sleep(0)
    new = asyncio.create_task(tts.speak("Câu mới."))
    await asyncio.sleep(0)
    tts.gates["Câu mới."].set()  # câu mới tổng hợp xong trước
    await new
    tts.gates["Câu trả lời cũ rất dài."].set()  # câu cũ xong muộn → phải bị bỏ
    await old
    assert tts.played == ["Câu mới.".encode()]


@pytest.mark.asyncio
async def test_stop_cancels_reply_still_being_synthesized(tts):
    task = asyncio.create_task(tts.speak("Câu trả lời cũ."))
    await asyncio.sleep(0)
    tts.stop()  # người dùng gửi câu hỏi mới
    tts.gates["Câu trả lời cũ."].set()
    await task
    assert tts.played == []


@pytest.mark.asyncio
async def test_single_reply_is_still_played(tts):
    task = asyncio.create_task(tts.speak("Xin chào."))
    await asyncio.sleep(0)
    tts.gates["Xin chào."].set()
    await task
    assert tts.played == ["Xin chào.".encode()]
