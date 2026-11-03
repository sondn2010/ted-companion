"""`busy_slots` của [TED_SYNC_PLAN] từ cache lịch của module work CÙNG MÁY (Phase 05); không có module work → None
(khoá bị bỏ khỏi request, đúng skill: "chỉ có khi Ted lấy được lịch")."""

import logging
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Iterable, Optional

logger = logging.getLogger("ted")
MASKED_TITLE = "Bận"
DAYS_AHEAD = 7


def _sanitize(title: str) -> str:
    """Tiêu đề lịch là dữ liệu không tin cậy, sắp vào prompt [TED_SYNC_PLAN] → làm sạch như briefing của module work."""
    try:   # import lười: bản không có module work vẫn chạy được coach
        from src.engines.work.daily_briefing_builder import sanitize_untrusted_text
    except ImportError:
        return " ".join(title.replace("[", " ").replace("]", " ").split())[:120]
    return sanitize_untrusted_text(title)


def events_to_busy_slots(events: Iterable, share_titles: bool, tz: tzinfo) -> list[dict]:
    """Hàng cache lịch (start_at/end_at aware UTC, title, all_day) → [{start,end,title}] giờ địa phương có offset.
    Bỏ sự kiện cả ngày (Red Team #9, giống CalendarEventRepository.busy_slots); title thay bằng "Bận" nếu không cho chia sẻ."""
    slots = []
    for event in events:
        if event.all_day:
            continue
        end = event.end_at or event.start_at + timedelta(minutes=60)
        slots.append({
            "start": event.start_at.astimezone(tz).isoformat(timespec="minutes"),
            "end": end.astimezone(tz).isoformat(timespec="minutes"),
            "title": (_sanitize(event.title or "") or MASKED_TITLE) if share_titles else MASKED_TITLE,
        })
    return slots


def collect_busy_slots(registry, db_engine, now: datetime, tz: tzinfo) -> Optional[list[dict]]:
    """None nếu không có module work đang bật hoặc cache không đọc được (khi đó request không có `busy_slots`)."""
    try:
        works = registry.find_by_engine("work") if registry is not None else []
        if not works:
            return None
        # Import lười: bản không có module work vẫn chạy được coach
        from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventRepository, event_end

        start = now.astimezone(timezone.utc)
        rows = CalendarEventRepository(db_engine).between(start - timedelta(hours=24), start + timedelta(days=DAYS_AHEAD))
        upcoming = [row for row in rows if event_end(row) > start]
        return events_to_busy_slots(upcoming, bool(works[0].settings.get("share_meeting_titles", False)), tz)
    except Exception:
        logger.exception("Không lấy được busy_slots, bỏ qua trong yêu cầu sync")
        return None
