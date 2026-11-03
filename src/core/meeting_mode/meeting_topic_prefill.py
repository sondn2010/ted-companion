"""Gợi ý chủ đề cho popup Họp: tên sự kiện lịch đang diễn ra (cache lịch Work) → không có thì chủ đề dùng lần trước."""

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.engine import Engine

from src.core.meeting_mode.meeting_session_table_model_and_repository import MeetingSessionRepository

logger = logging.getLogger("ted")


def current_calendar_event_title(engine: Engine, now_utc: Optional[datetime] = None) -> str:
    """Tên sự kiện (không cả ngày) đã bắt đầu và chưa kết thúc; lỗi/không có → ''. Lịch là nguồn phụ nên không raise."""
    try:
        from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventRepository, event_end
        now = now_utc or datetime.now(timezone.utc)
        events = [e for e in CalendarEventRepository(engine).overlapping(now)
                  if e.start_at <= now <= event_end(e) and e.title.strip()]
        return max(events, key=lambda e: e.start_at).title.strip() if events else ""
    except Exception:  # noqa: BLE001
        logger.warning("Không đọc được lịch để gợi ý chủ đề họp", exc_info=True)
        return ""


def meeting_prefill(engine: Engine, now_utc: Optional[datetime] = None) -> Tuple[str, str]:
    """(topic, kind) cho popup: kind luôn là lần dùng gần nhất; topic ưu tiên sự kiện lịch đang diễn ra."""
    kind, last_topic = MeetingSessionRepository(engine).last_used()
    return current_calendar_event_title(engine, now_utc) or last_topic, kind
