"""Đọc theo khúc: khúc đầu phát ngay khi tổng hợp xong (không chờ hết bài), khúc sau phát nối tiếp đúng thứ tự;
dừng / câu mới xoá hàng đợi."""

import asyncio

import pytest

from src.config import settings
from src.core.tts_chunk_playback_queue import ChunkPlaybackQueue
from src.core.tts_service import TTSService
from tests.qt_offscreen_app_helper import get_qapp


class _Speaker:
    def __init__(self):
        self.played: list[bytes] = []
        self.busy = False

    def play(self, data: bytes) -> None:
        self.played.append(data)
        self.busy = True


def _queue():
    spk = _Speaker()
    return ChunkPlaybackQueue(play=spk.play, is_busy=lambda: spk.busy), spk


def test_first_chunk_plays_immediately_rest_queue_in_order():
    q, spk = _queue()
    q.deliver(b"c1", 1, 1)
    q.deliver(b"c2", 1, 1)
    q.deliver(b"c3", 1, 1)
    assert spk.played == [b"c1"] and q.has_pending
    spk.busy = False
    q.on_playback_finished(1)
    assert spk.played == [b"c1", b"c2"]
    spk.busy = False
    q.on_playback_finished(1)
    assert spk.played == [b"c1", b"c2", b"c3"] and not q.has_pending


def test_chunk_arriving_after_speaker_idle_plays_right_away():
    q, spk = _queue()
    q.deliver(b"c1", 1, 1)
    spk.busy = False
    q.on_playback_finished(1)   # khúc 1 hết, khúc 2 chưa tổng hợp xong
    q.deliver(b"c2", 1, 1)
    assert spk.played == [b"c1", b"c2"]


def test_new_generation_interrupts_and_drops_old_queue():
    q, spk = _queue()
    q.deliver(b"old1", 1, 1)
    q.deliver(b"old2", 1, 1)
    q.deliver(b"new1", 2, 2)    # câu mới: phát đè ngay, bỏ khúc cũ đang chờ
    assert spk.played == [b"old1", b"new1"]
    spk.busy = False
    q.on_playback_finished(2)
    assert spk.played == [b"old1", b"new1"]


def test_stale_generation_chunks_are_ignored_and_finish_after_stop_clears():
    q, spk = _queue()
    q.deliver(b"c1", 1, 1)
    q.deliver(b"c2", 1, 1)
    assert not q.deliver(b"late", 1, 2)   # đã stop() (lượt 2) → khúc muộn của lượt 1 bị bỏ
    q.on_playback_finished(2)
    assert spk.played == [b"c1"] and not q.has_pending


def test_first_chunk_is_short_for_fast_first_audio_and_text_is_preserved():
    from src.core.vieneu_text_chunking_and_wav_concat import split_text_for_tts
    text = " ".join(f"Đây là câu số {i} khá là dài để thử cắt khúc." for i in range(40))
    chunks = split_text_for_tts(text, first_limit=120)
    assert len(chunks[0]) <= 120 and all(len(c) <= 350 for c in chunks[1:])
    assert len(chunks[1]) > 120                       # khúc sau vẫn gộp dài cho giọng liền mạch
    assert " ".join(chunks) == text
    assert split_text_for_tts("Ngắn thôi.", first_limit=120) == ["Ngắn thôi."]
    long_sentence = "Một câu rất dài, " * 30 + "hết."   # không có dấu chấm sớm: cắt ở dấu phẩy
    first, *rest = split_text_for_tts(long_sentence, first_limit=120)
    assert len(first) <= 120 and " ".join([first, *rest]) == long_sentence.strip()


def test_service_awaiting_playback_counts_as_busy_until_player_reports(monkeypatch):
    get_qapp()
    tts = TTSService()
    tts._awaiting_playback = True
    assert tts._player_busy() and tts.is_speaking()
    from PySide6.QtMultimedia import QMediaPlayer
    tts._on_media_status_changed(QMediaPlayer.MediaStatus.InvalidMedia)   # lỗi phát → không kẹt "bận" mãi
    assert not tts._player_busy()


class _ChunkedTTS(TTSService):
    """Engine giả đọc theo khúc: mỗi khúc chờ 1 Event để test điều khiển thời điểm tổng hợp xong."""

    def __init__(self, n_chunks: int):
        super().__init__()
        self.gates = [asyncio.Event() for _ in range(n_chunks)]
        self.played: list[bytes] = []
        self.busy = False

    async def synthesize(self, text, lang=None, voice=None, should_continue=None, on_chunk=None, **_kw):
        for i, gate in enumerate(self.gates):
            await gate.wait()
            if should_continue and not should_continue():
                return b""
            on_chunk(f"RIFF-chunk{i}".encode())
        return b""

    def _play_bytes(self, data: bytes) -> None:
        self.played.append(data)
        self.busy = True

    def _player_busy(self) -> bool:
        return self.busy


@pytest.fixture
def tts_on(monkeypatch):
    get_qapp()
    monkeypatch.setattr(settings, "tts_enabled", True, raising=False)


async def test_speak_plays_first_chunk_before_rest_is_synthesized(tts_on):
    tts = _ChunkedTTS(3)
    task = asyncio.create_task(tts.speak("Câu dài gồm ba khúc."))
    await asyncio.sleep(0)
    tts.gates[0].set()
    await asyncio.sleep(0)
    assert tts.played == [b"RIFF-chunk0"]   # đã có tiếng trong khi khúc 2, 3 còn đang tổng hợp
    assert tts.is_speaking()
    tts.gates[1].set()
    tts.gates[2].set()
    await task
    assert tts.played == [b"RIFF-chunk0"] and tts._chunk_queue.has_pending   # khúc 2, 3 chờ loa rảnh
    tts.busy = False
    tts._chunk_queue.on_playback_finished(tts._generation)
    tts.busy = False
    tts._chunk_queue.on_playback_finished(tts._generation)
    assert tts.played == [b"RIFF-chunk0", b"RIFF-chunk1", b"RIFF-chunk2"]


async def test_stop_mid_reply_drops_queued_and_unsynthesized_chunks(tts_on):
    tts = _ChunkedTTS(3)
    task = asyncio.create_task(tts.speak("Câu dài gồm ba khúc."))
    await asyncio.sleep(0)
    tts.gates[0].set()
    tts.gates[1].set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    tts.stop()   # click Ted / gửi câu hỏi mới
    tts.gates[2].set()
    await task
    tts.busy = False
    tts._chunk_queue.on_playback_finished(tts._generation)
    assert tts.played == [b"RIFF-chunk0"]
    assert not tts.is_speaking()
