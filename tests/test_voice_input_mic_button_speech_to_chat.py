"""Nút 🎤 nói thay vì gõ: ẩn khi chưa bật STT, ghi âm → ⏹ → STT → chữ vào ô nhập; lỗi/ghi quá ngắn báo nhẹ trong ô."""

import asyncio

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QLineEdit

from qt_offscreen_app_helper import flush_qt_garbage, get_qapp

from src.config import settings
from src.core.background_task_spawner import _running_tasks
from src.core.microphone_wav_recorder import SAMPLE_RATE, pcm16_mono_to_wav
from src.ui.voice_input_mic_button import VoiceInputMicButton


@pytest.fixture(autouse=True)
def _flush_widgets_after_test():
    yield
    flush_qt_garbage()


class _FakeRecorder(QObject):
    auto_stopped = Signal()

    def __init__(self, seconds: float = 1.0):
        super().__init__()
        self.is_recording = False
        self._seconds = seconds

    def start(self):
        self.is_recording = True

    def stop(self):
        self.is_recording = False
        return pcm16_mono_to_wav(b"\x00\x00" * int(SAMPLE_RATE * self._seconds))


class _FakeStt:
    def __init__(self, text="", error=None):
        self.text, self.error, self.calls = text, error, []

    async def transcribe_bytes(self, audio, filename="", language=None, http_client=None):
        self.calls.append((audio[:4], language))
        if self.error:
            raise self.error
        return self.text


def _button(monkeypatch, recorder=None, stt=None, enabled=True):
    get_qapp()
    monkeypatch.setattr(settings, "stt_enabled", enabled)
    monkeypatch.setattr(settings, "stt_language", "vi")
    field = QLineEdit()
    field.setPlaceholderText("Nhắn cho Ted")
    return field, VoiceInputMicButton(field, recorder=recorder or _FakeRecorder(), stt=stt or _FakeStt("Xin chào Ted"))


def test_wav_header_is_16khz_mono_pcm():
    wav = pcm16_mono_to_wav(b"\x01\x00" * 10)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE" and len(wav) == 44 + 20
    assert int.from_bytes(wav[24:28], "little") == SAMPLE_RATE and int.from_bytes(wav[22:24], "little") == 1


def test_mic_hidden_until_stt_enabled(monkeypatch):
    _field, button = _button(monkeypatch, enabled=False)
    assert button.isHidden()
    monkeypatch.setattr(settings, "stt_enabled", True)
    button.refresh_visibility()
    assert not button.isHidden()


async def test_record_stop_transcribes_into_input(monkeypatch):
    stt = _FakeStt("giải phương trình x bình phương")
    field, button = _button(monkeypatch, stt=stt)
    field.setText("Ted ơi")
    button.click()
    assert button.text() == "⏹" and "Đang nghe" in field.placeholderText()
    button.click()
    await asyncio.gather(*list(_running_tasks))
    assert field.text() == "Ted ơi giải phương trình x bình phương"
    assert stt.calls == [(b"RIFF", "vi")] and button.text() == "🎤" and button.isEnabled()
    assert field.placeholderText() == "Nhắn cho Ted"


async def test_short_recording_and_errors_show_hint_without_crash(monkeypatch):
    field, button = _button(monkeypatch, recorder=_FakeRecorder(seconds=0.05))
    button.click()
    button.click()
    assert "Chưa nghe thấy" in field.placeholderText() and field.text() == ""

    field, button = _button(monkeypatch, stt=_FakeStt(error=RuntimeError("Chưa tải mô hình")))
    button.click()
    button.click()
    await asyncio.gather(*list(_running_tasks))
    assert "Chưa tải mô hình" in field.placeholderText() and button.isEnabled()


def test_quick_chat_and_bubble_have_mic_button():
    get_qapp()
    from types import SimpleNamespace
    from src.ui.pet_speech_bubble_widget import PetSpeechBubble
    from src.ui.quick_chat_popup import QuickChatPopup

    class _Focus(QObject):
        character_changed = Signal(str)

    popup = QuickChatPopup(_Focus(), SimpleNamespace(for_module=lambda _m: None), SimpleNamespace(active=lambda: None))
    assert isinstance(popup.btn_mic, VoiceInputMicButton) and popup.btn_mic._target is popup.input_chat
    assert isinstance(PetSpeechBubble().btn_mic, VoiceInputMicButton)
