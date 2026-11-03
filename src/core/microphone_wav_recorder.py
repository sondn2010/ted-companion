"""Ghi âm micro thành WAV 16kHz mono 16-bit (định dạng whisper.cpp & máy chủ STT đều nhận) bằng QtMultimedia.

Dùng cho nút 🎤 trong ô chat: start() → người dùng nói → stop() trả bytes WAV. Tự dừng sau MAX_SECONDS.
"""

import logging
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices

logger = logging.getLogger("ted")

SAMPLE_RATE = 16000
MAX_SECONDS = 60


def pcm16_mono_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Bọc PCM 16-bit mono bằng header WAV (RIFF) chuẩn."""
    byte_rate = sample_rate * 2
    header = (
        b"RIFF" + (36 + len(pcm)).to_bytes(4, "little") + b"WAVEfmt "
        + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
        + sample_rate.to_bytes(4, "little") + byte_rate.to_bytes(4, "little")
        + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
        + b"data" + len(pcm).to_bytes(4, "little")
    )
    return header + pcm


def has_microphone() -> bool:
    return not QMediaDevices.defaultAudioInput().isNull()


class MicrophoneWavRecorder(QObject):
    auto_stopped = Signal()   # hết MAX_SECONDS: nơi dùng gọi stop() để lấy âm thanh

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._source: Optional[QAudioSource] = None
        self._io = None
        self._buffer = bytearray()
        self._limit = QTimer(self)
        self._limit.setSingleShot(True)
        self._limit.timeout.connect(self.auto_stopped)

    @property
    def is_recording(self) -> bool:
        return self._source is not None

    def start(self) -> None:
        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            raise RuntimeError("Không tìm thấy micro trên máy.")
        fmt = QAudioFormat()
        fmt.setSampleRate(SAMPLE_RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            raise RuntimeError("Micro không hỗ trợ ghi 16kHz mono.")
        self._buffer.clear()
        self._source = QAudioSource(device, fmt, self)
        self._io = self._source.start()
        if self._io is None:
            self._source = None
            raise RuntimeError("Không mở được micro (kiểm tra quyền truy cập micro của hệ điều hành).")
        self._io.readyRead.connect(self._read)
        self._limit.start(MAX_SECONDS * 1000)

    def _read(self) -> None:
        if self._io is not None:
            self._buffer.extend(bytes(self._io.readAll()))

    def stop(self) -> bytes:
        """Dừng ghi; trả WAV (rỗng nếu chưa ghi được gì)."""
        self._limit.stop()
        if self._source is None:
            return b""
        self._read()
        self._source.stop()
        self._source.deleteLater()
        self._source, self._io = None, None
        return pcm16_mono_to_wav(bytes(self._buffer)) if self._buffer else b""
