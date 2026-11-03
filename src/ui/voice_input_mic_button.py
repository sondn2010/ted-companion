"""Nút 🎤 nói thay vì gõ: bấm → ghi âm micro → bấm ⏹ → STT (offline whisper.cpp hoặc máy chủ) → chèn chữ vào ô nhập.

Chỉ hiện khi đã bật Nhận giọng nói (Cài đặt → 🎙️ Nhận giọng nói). Người dùng xem lại chữ rồi tự bấm Gửi.
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QPushButton, QWidget

from src.config import settings
from src.core.background_task_spawner import spawn_background_task
from src.core.i18n import tr
from src.core.microphone_wav_recorder import SAMPLE_RATE, MicrophoneWavRecorder

MIN_AUDIO_BYTES = 44 + int(SAMPLE_RATE * 2 * 0.3)   # < 0,3 giây coi như chưa nói gì


def is_stt_ready() -> bool:
    return bool(getattr(settings, "stt_enabled", False))


class VoiceInputMicButton(QPushButton):
    def __init__(self, target: QLineEdit, parent: Optional[QWidget] = None, recorder=None, stt=None):
        super().__init__("🎤", parent)
        self._target = target
        self._recorder = recorder or MicrophoneWavRecorder(self)
        self._recorder.auto_stopped.connect(self._finish_recording)
        self._stt = stt
        self._placeholder = target.placeholderText()
        self.setObjectName("IconBtn")
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("mic_btn_tooltip"))
        self.clicked.connect(self._on_clicked)
        self.refresh_visibility()

    def refresh_visibility(self) -> None:
        self.setVisible(is_stt_ready() or self._recorder.is_recording)

    def _service(self):
        if self._stt is None:
            from src.core.stt_service import stt_service
            self._stt = stt_service
        return self._stt

    def _on_clicked(self) -> None:
        if self._recorder.is_recording:
            self._finish_recording()
            return
        try:
            self._recorder.start()
        except Exception as exc:
            self._show_hint(f"🎤 {exc}")
            return
        self._placeholder = self._target.placeholderText()
        self.setText("⏹")
        self.setToolTip(tr("mic_btn_stop_tooltip"))
        self._target.setPlaceholderText(tr("mic_listening"))

    def _finish_recording(self) -> None:
        if not self._recorder.is_recording:
            return
        wav = self._recorder.stop()
        self.setText("🎤")
        self.setToolTip(tr("mic_btn_tooltip"))
        if len(wav) < MIN_AUDIO_BYTES:
            self._show_hint(tr("mic_too_short"))
            return
        self.setEnabled(False)
        self._target.setPlaceholderText(tr("mic_transcribing"))
        spawn_background_task(self.transcribe_into_target(wav), "voice-input-stt")

    async def transcribe_into_target(self, wav: bytes) -> str:
        language = getattr(settings, "stt_language", "vi")
        try:
            text = (await self._service().transcribe_bytes(
                wav, filename="mic.wav", language=None if language == "auto" else language)).strip()
        except Exception as exc:
            self._show_hint(tr("mic_failed", error=str(exc)[:120]))
            return ""
        finally:
            self.setEnabled(True)
        if not text:
            self._show_hint(tr("mic_nothing_heard"))
            return ""
        current = self._target.text().strip()
        self._target.setText(f"{current} {text}".strip())
        self._target.setPlaceholderText(self._placeholder)
        self._target.setFocus()
        return text

    def _show_hint(self, message: str) -> None:
        """Báo lỗi/gợi ý ngay trong ô nhập (placeholder) — không bật hộp thoại chặn luồng chat."""
        self._target.setPlaceholderText(message)
        self.setToolTip(message)
