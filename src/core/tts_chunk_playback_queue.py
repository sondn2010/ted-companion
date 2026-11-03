"""Hàng đợi phát âm thanh theo khúc: engine đọc theo khúc (VieNeu) giao từng khúc WAV ngay khi có,
khúc đầu phát liền (không chờ tổng hợp hết bài), các khúc sau xếp hàng phát nối tiếp.

Quy tắc theo "lượt" (generation của TTSService — tăng mỗi lần speak()/stop()):
- Khúc của lượt cũ → bỏ (người dùng đã bấm dừng / có câu mới hơn).
- Khúc đầu tiên của lượt mới → xoá hàng đợi cũ và phát ngay (câu mới thắng câu cũ).
- Khúc tiếp theo cùng lượt → phát ngay nếu loa rảnh, không thì xếp hàng; loa phát xong → lấy khúc kế.
Không phụ thuộc Qt: TTSService truyền hàm play/is_busy để dễ kiểm thử.
"""

from collections import deque
from typing import Callable


class ChunkPlaybackQueue:
    def __init__(self, play: Callable[[bytes], None], is_busy: Callable[[], bool]):
        self._play = play
        self._is_busy = is_busy
        self._pending: deque[bytes] = deque()
        self._playing_generation = -1

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    def deliver(self, data: bytes, generation: int, current_generation: int) -> bool:
        """Nhận 1 khúc âm thanh; trả True nếu khúc được phát ngay hoặc xếp hàng."""
        if not data or generation != current_generation:
            return False
        if generation != self._playing_generation:   # khúc đầu của câu mới: đè câu cũ
            self._pending.clear()
            self._playing_generation = generation
            self._play(data)
        elif self._is_busy() or self._pending:      # giữ đúng thứ tự khúc
            self._pending.append(data)
        else:
            self._play(data)
        return True

    def on_playback_finished(self, current_generation: int) -> None:
        """Loa phát xong 1 khúc → phát khúc kế của đúng lượt hiện tại (nếu còn)."""
        if self._playing_generation != current_generation:
            self._pending.clear()
            return
        if self._pending:
            self._play(self._pending.popleft())

    def clear(self) -> None:
        self._pending.clear()
