"""Nhắc họp T-15/T-5 từ cache cục bộ (không cần mạng). Họp quan trọng hơn tập trung → luôn hiện, kể cả khi Deep Work."""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from PySide6.QtCore import QObject, QTimer

from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventRepository
from src.engines.work.daily_briefing_builder import sanitize_untrusted_text
from src.engines.work.meeting_link_opener import open_meeting_link
from src.engines.work.meeting_reminder_timing import compute_due_reminders, minutes_until

logger = logging.getLogger("ted")
TICK_MS = 30_000
REMINDED_KEY = "work.reminded:{day}"
KEEP_DAYS = 2  # đọc hợp nhất hôm nay + 2 ngày trước (họp sau nửa đêm nhắc từ tối hôm trước)
REMINDER_BUBBLE_MS = 20_000


class MeetingReminderService(QObject):
    def __init__(self, ctx, repo: CalendarEventRepository, offsets: list[int]):
        super().__init__()
        self._ctx = ctx
        self._repo = repo
        self._offsets = sorted({int(o) for o in offsets if int(o) > 0}, reverse=True)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._prune_old_keys(date.today())

    def start(self) -> None:
        if self._offsets:
            self._timer.start(TICK_MS)

    def stop(self) -> None:
        self._timer.stop()

    # ---- KV: các khoá đã bắn, chia theo ngày local ----
    def _day_key(self, day: date) -> str:
        return REMINDED_KEY.format(day=day.isoformat())

    def _load_fired(self, today: date) -> set[str]:
        fired: set[str] = set()
        for back in range(KEEP_DAYS + 1):
            value = self._ctx.kv.get_json(self._day_key(today - timedelta(days=back)), [])
            if isinstance(value, list):
                fired.update(k for k in value if isinstance(k, str))
        return fired

    def _prune_old_keys(self, today: date) -> None:
        """Ngày quá cũ → xoá nội dung (KV không có delete)."""
        for back in range(KEEP_DAYS + 1, KEEP_DAYS + 6):
            key = self._day_key(today - timedelta(days=back))
            if self._ctx.kv.get(key) not in (None, "[]"):
                self._ctx.kv.set_json(key, [])

    # ---- tick ----
    def tick(self, now: Optional[datetime] = None) -> int:
        """Bắn các nhắc đến hạn; trả số sự kiện đã nhắc. Lỗi nội bộ không được làm sập timer."""
        try:
            return self._tick(now or datetime.now(timezone.utc))
        except Exception:
            logger.exception("Lỗi khi kiểm tra nhắc họp")
            return 0

    def _tick(self, now: datetime) -> int:
        horizon = now + timedelta(minutes=max(self._offsets) + 1)
        today = now.astimezone().date()
        fired = self._load_fired(today)
        due = compute_due_reminders(self._repo.between(now, horizon), now, self._offsets, fired)
        if not due:
            return 0
        marked = set().union(*(keys for _ev, _o, keys in due))
        today_key = self._day_key(today)
        self._ctx.kv.set_json(today_key, sorted(set(self._ctx.kv.get_json(today_key, [])) | marked))
        self._announce([(ev, minutes_until(ev.start_at, now)) for ev, _o, _k in due])
        return len(due)

    def _announce(self, items: list) -> None:
        lines = [
            f"⏰ {mins} phút nữa: {sanitize_untrusted_text(ev.title) or '(không tên)'} ({ev.start_at.astimezone():%H:%M})"
            for ev, mins in items
        ]
        links = [ev for ev, _m in items if ev.meet_url]
        actions = [
            ("Mở link họp" if len(links) == 1 else f"Mở link: {sanitize_untrusted_text(ev.title)[:15]}",
             lambda url=ev.meet_url: open_meeting_link(url))
            for ev in links
        ]
        audio, bubble = self._ctx.audio, self._ctx.bubble
        if audio is not None:
            audio.play_chime()
        if bubble is not None:
            bubble.show_message("\n".join(lines), mood="GENTLE_NUDGE", actions=actions, timeout_ms=REMINDER_BUBBLE_MS)
