"""Phát liền mạch các khúc WAV của cùng một câu trả lời: đẩy PCM nối đuôi vào một QAudioSink duy nhất.

Vì sao: QMediaPlayer phát từng khúc là 1 file → hết khúc mới stop/setSource/play khúc kế, mất ~100–300 ms
mỗi lần nên giọng bị ngắt ở mọi dấu chấm câu. Ở đây khúc kế (đã tổng hợp sẵn trong lúc khúc hiện tại đang đọc)
được nối thẳng vào bộ đệm âm thanh → không còn khoảng lặng do trình phát.

- append_wav(data, restart): restart=True = câu mới, bỏ âm thanh cũ. Trả False nếu không phải WAV PCM
  hoặc máy không phát được định dạng đó → TTSService quay về QMediaPlayer.
- Mỗi khúc VieNeu có sẵn ~70–90 ms lặng đầu + ~170–200 ms lặng cuối → nối thẳng vẫn hụt ~0,3 s ở mỗi chỗ nối;
  cắt bớt lặng ở mép khúc (Int16) chỉ giữ một nhịp nghỉ tự nhiên.
- Hết dữ liệu và loa phát xong → giải phóng sink, phát tín hiệu `finished`.
"""

import array
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices, QtAudio

from src.core.vieneu_text_chunking_and_wav_concat import parse_wav

_FEED_INTERVAL_MS = 15
_SINK_BUFFER_SECONDS = 0.3   # đệm đủ dày để UI khựng chốc lát không làm vấp tiếng
_KEEP_LEAD_MS = 20    # giữ chút lặng trước tiếng để không mất phụ âm đầu
_KEEP_TAIL_MS = 150   # nhịp nghỉ giữa hai câu (tương đương ngắt câu bên trong một khúc)
_SILENCE_RATIO = 0.02  # mẫu < 2% đỉnh của khúc coi là lặng


def trim_edge_silence_int16(pcm: bytes, sample_rate: int, channels: int,
                            keep_lead_ms: int = _KEEP_LEAD_MS, keep_tail_ms: int = _KEEP_TAIL_MS) -> bytes:
    """Cắt lặng đầu/cuối của PCM Int16 xen kênh, giữ lại keep_*_ms. Toàn lặng / dữ liệu lẻ → trả nguyên."""
    frame = 2 * channels
    if channels < 1 or len(pcm) < frame or len(pcm) % frame:
        return pcm
    samples = array.array("h", pcm)
    peak = max(abs(min(samples)), max(samples))
    if peak == 0:
        return pcm
    threshold = peak * _SILENCE_RATIO
    # Duyệt từ hai đầu vào, dừng ở mẫu "có tiếng" đầu tiên (chỉ quét phần lặng, không quét cả khúc)
    first = next(i for i, s in enumerate(samples) if abs(s) > threshold)
    last = next(i for i in range(len(samples) - 1, -1, -1) if abs(samples[i]) > threshold)
    first_frame, last_frame = first // channels, last // channels
    total_frames = len(samples) // channels
    start = max(0, first_frame - sample_rate * keep_lead_ms // 1000)
    end = min(total_frames, last_frame + 1 + sample_rate * keep_tail_ms // 1000)
    return pcm[start * frame:end * frame]

# bits/sample (+ cờ float) → định dạng mẫu Qt
_SAMPLE_FORMATS = {
    (8, False): QAudioFormat.SampleFormat.UInt8,
    (16, False): QAudioFormat.SampleFormat.Int16,
    (32, False): QAudioFormat.SampleFormat.Int32,
    (32, True): QAudioFormat.SampleFormat.Float,
}


def _audio_format_from_wav_fmt(fmt_chunk: bytes) -> Optional[QAudioFormat]:
    """Chunk 'fmt ' của WAV → QAudioFormat; None nếu không phải PCM/float hỗ trợ."""
    if len(fmt_chunk) < 16:
        return None
    tag = int.from_bytes(fmt_chunk[0:2], "little")
    if tag == 0xFFFE and len(fmt_chunk) >= 26:   # WAVE_FORMAT_EXTENSIBLE: mã thật nằm trong sub-format
        tag = int.from_bytes(fmt_chunk[24:26], "little")
    sample_format = _SAMPLE_FORMATS.get((int.from_bytes(fmt_chunk[14:16], "little"), tag == 3))
    if tag not in (1, 3) or sample_format is None:
        return None
    fmt = QAudioFormat()
    fmt.setChannelCount(int.from_bytes(fmt_chunk[2:4], "little"))
    fmt.setSampleRate(int.from_bytes(fmt_chunk[4:8], "little"))
    fmt.setSampleFormat(sample_format)
    return fmt


class GaplessPcmStreamPlayer(QObject):
    finished = Signal()

    def __init__(self, volume: float = 0.9, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._volume = volume
        self._sink: Optional[QAudioSink] = None
        self._io = None
        self._fmt_chunk: Optional[bytes] = None
        self._buffer = bytearray()
        self._written_bytes = 0
        self._timer = QTimer(self)
        self._timer.setInterval(_FEED_INTERVAL_MS)
        self._timer.timeout.connect(self._feed)

    def is_busy(self) -> bool:
        return self._sink is not None

    def append_wav(self, data: bytes, restart: bool) -> bool:
        try:
            fmt_chunk, pcm = parse_wav(data)
        except ValueError:
            return False
        if restart or fmt_chunk != self._fmt_chunk or self._sink is None:
            if not restart and self._sink is not None:
                return False   # khác định dạng giữa chừng: không nối được, để QMediaPlayer lo
            self.stop()
            if not self._open_sink(fmt_chunk):
                return False
        fmt = self._sink.format()
        if fmt.sampleFormat() == QAudioFormat.SampleFormat.Int16:
            pcm = trim_edge_silence_int16(pcm, fmt.sampleRate(), fmt.channelCount())
        self._buffer += pcm
        self._feed()
        return True

    def stop(self) -> None:
        self._timer.stop()
        self._buffer.clear()
        if self._sink is not None:
            self._sink.stop()
            self._sink.deleteLater()
        self._sink, self._io, self._fmt_chunk, self._written_bytes = None, None, None, 0

    def _open_sink(self, fmt_chunk: bytes) -> bool:
        fmt = _audio_format_from_wav_fmt(fmt_chunk)
        device = QMediaDevices.defaultAudioOutput()
        if fmt is None or device.isNull() or not device.isFormatSupported(fmt):
            return False
        sink = QAudioSink(device, fmt, self)
        sink.setVolume(self._volume)
        sink.setBufferSize(int(fmt.bytesForDuration(int(_SINK_BUFFER_SECONDS * 1_000_000))))
        io = sink.start()   # push mode: tự ghi PCM vào io theo nhịp timer
        if io is None or sink.error() != QtAudio.Error.NoError:
            sink.deleteLater()
            return False
        self._sink, self._io, self._fmt_chunk = sink, io, fmt_chunk
        self._timer.start()
        return True

    def _feed(self) -> None:
        sink = self._sink
        if sink is None:
            return
        if self._buffer:
            n = min(sink.bytesFree(), len(self._buffer))
            if n > 0:
                written = self._io.write(bytes(self._buffer[:n]))
                if written > 0:
                    del self._buffer[:written]
                    self._written_bytes += written
            return
        # Hết dữ liệu: chờ loa phát nốt phần đã ghi (Idle = cạn đệm) rồi mới báo xong
        played_all = sink.processedUSecs() >= sink.format().durationForBytes(self._written_bytes)
        if sink.state() == QtAudio.State.IdleState or played_all:
            self.stop()
            self.finished.emit()
