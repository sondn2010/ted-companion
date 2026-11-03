"""Timer 60s kiểm tra slot briefing đến hạn (sáng/trưa) + kiểm tra sớm ngay sau khi app mở (bắt kịp briefing bị lỡ)."""

import logging
from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import QTimer

from src.engines.work.work_briefing_due_window import due_briefing_slot

logger = logging.getLogger("ted")
CHECK_INTERVAL_MS = 60_000
FIRST_CHECK_DELAY_MS = 8_000  # sau lần sync lịch đầu (5s) để họp hôm nay đã có trong cache


class ScheduledBriefingTimer:
    """last_dates() → (ngày sáng đã bắn, ngày trưa đã bắn); fire(slot) chịu trách nhiệm ghi KV + hiện briefing."""

    def __init__(
        self,
        settings,
        last_dates: Callable[[], tuple[Optional[str], Optional[str]]],
        fire: Callable[[str], None],
        clock: Callable[[], datetime] = lambda: datetime.now().astimezone(),
        last_briefing_at: Callable[[], Optional[datetime]] = lambda: None,
    ):
        self._settings = settings
        self._last_dates = last_dates
        self._fire = fire
        self._clock = clock
        self._last_briefing_at = last_briefing_at
        self._first: Optional[QTimer] = None
        self._timer: Optional[QTimer] = None

    def start(self) -> None:
        if self._timer is not None:  # chống start 2 lần
            return
        self._first = QTimer()
        self._first.setSingleShot(True)
        self._first.timeout.connect(self.check_now)
        self._first.start(FIRST_CHECK_DELAY_MS)
        self._timer = QTimer()
        self._timer.timeout.connect(self.check_now)
        self._timer.start(CHECK_INTERVAL_MS)

    def stop(self) -> None:
        for timer in (self._first, self._timer):
            if timer is not None:
                timer.stop()
        self._first = self._timer = None

    def check_now(self) -> Optional[str]:
        """Bắn slot đến hạn (nếu có) và trả slot đó. Lỗi không được làm chết timer."""
        try:
            morning, midday = self._last_dates()
            slot = due_briefing_slot(self._clock(), self._settings, morning, midday, self._last_briefing_at())
            if slot:
                self._fire(slot)
            return slot
        except Exception:
            logger.exception("Kiểm tra briefing định kỳ lỗi")
            return None
