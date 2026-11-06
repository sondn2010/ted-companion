"""Đọc liền mạch: khúc WAV nối thẳng vào một luồng PCM (không ngắt ở dấu câu), lặng ở mép khúc được cắt bớt;
MP3 / dữ liệu lạ vẫn đi QMediaPlayer; khúc của lượt cũ bị bỏ."""

import io
import struct
import wave

from src.core.tts_gapless_pcm_stream_player import _audio_format_from_wav_fmt, trim_edge_silence_int16
from src.core.tts_service import TTSService
from src.core.vieneu_text_chunking_and_wav_concat import parse_wav
from tests.qt_offscreen_app_helper import get_qapp

SR = 1000   # 1 mẫu = 1 ms cho dễ đọc


def _wav(samples: list[int], sr: int = SR) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def _pcm(samples: list[int]) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


def test_trim_keeps_short_lead_and_natural_tail_pause():
    voiced = [8000, -8000] * 50                     # 100 ms có tiếng
    pcm = _pcm([0] * 90 + voiced + [3] * 200)      # 90 ms lặng đầu, 200 ms gần lặng cuối
    out = trim_edge_silence_int16(pcm, SR, 1, keep_lead_ms=20, keep_tail_ms=150)
    assert len(out) // 2 == 20 + 100 + 150
    assert out[40:240] == _pcm(voiced)            # phần có tiếng giữ nguyên


def test_trim_leaves_silent_or_short_edges_untouched():
    assert trim_edge_silence_int16(_pcm([0] * 50), SR, 1) == _pcm([0] * 50)
    tight = _pcm([9000] * 30)
    assert trim_edge_silence_int16(tight, SR, 1) == tight
    assert trim_edge_silence_int16(b"\x01\x02\x03", SR, 1) == b"\x01\x02\x03"   # lẻ byte: không đụng


def test_wav_fmt_maps_to_qt_audio_format():
    get_qapp()
    fmt_chunk, _ = parse_wav(_wav([0] * 10, sr=24000))
    fmt = _audio_format_from_wav_fmt(fmt_chunk)
    assert fmt is not None and fmt.sampleRate() == 24000 and fmt.channelCount() == 1


class _FakePcmStream:
    """Luồng PCM giả: nhận mọi WAV hợp lệ, ghi lại thứ tự / lần bắt đầu lại."""

    def __init__(self):
        self.appended: list[tuple[bytes, bool]] = []
        self.stopped = 0

    def append_wav(self, data: bytes, restart: bool) -> bool:
        if not data.startswith(b"RIFF") or len(data) < 44:
            return False
        self.appended.append((data, restart))
        return True

    def stop(self) -> None:
        self.stopped += 1

    def is_busy(self) -> bool:
        return bool(self.appended)


def _service():
    get_qapp()
    tts = TTSService()
    tts._pcm_stream = _FakePcmStream()
    tts.played = []
    tts._play_bytes = tts.played.append
    return tts


def test_wav_chunks_of_one_reply_go_to_one_continuous_stream():
    tts = _service()
    tts._generation = 1
    a, b, c = _wav([1] * 5), _wav([2] * 5), _wav([3] * 5)
    for chunk in (a, b, c):
        tts._deliver_audio(chunk, 1)
    assert tts._pcm_stream.appended == [(a, True), (b, False), (c, False)]   # chỉ khúc đầu bắt đầu luồng mới
    assert tts.played == [] and tts.is_speaking()


def test_new_reply_restarts_stream_and_stale_chunks_are_dropped():
    tts = _service()
    tts._generation = 1
    tts._deliver_audio(_wav([1] * 5), 1)
    tts._generation = 2
    tts._deliver_audio(_wav([1] * 5), 1)            # khúc muộn của câu cũ
    new = _wav([7] * 5)
    tts._deliver_audio(new, 2)
    assert [r for _, r in tts._pcm_stream.appended] == [True, True]
    assert tts._pcm_stream.appended[-1] == (new, True)


def test_non_wav_audio_falls_back_to_media_player():
    tts = _service()
    tts._generation = 1
    tts._deliver_audio(b"ID3-mp3-bytes", 1)
    assert tts.played == [b"ID3-mp3-bytes"] and tts._pcm_stream.stopped == 1   # im luồng PCM của câu trước


def test_stop_also_silences_pcm_stream():
    tts = _service()
    tts._generation = 1
    tts._deliver_audio(_wav([1] * 5), 1)
    tts.stop()
    assert tts._pcm_stream.stopped == 1
