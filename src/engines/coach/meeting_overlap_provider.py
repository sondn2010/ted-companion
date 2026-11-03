"""Có đang trong cuộc họp (cache lịch của module work cùng máy) không. Không có module work đang bật → luôn False."""

import logging
from datetime import datetime

logger = logging.getLogger("ted")


def in_meeting(db_engine, now: datetime, registry=None) -> bool:
    """False nếu không có module work đang bật trên máy này (cache lịch còn sót không được làm coach im lặng)."""
    try:
        if registry is None or not registry.find_by_engine("work"):
            return False
    except Exception:
        logger.exception("Không kiểm tra được module work, coi như không họp")
        return False
    try:
        from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventRepository
    except ModuleNotFoundError:
        return False   # lazy import: không có module work/lịch thì không bao giờ "đang họp"
    try:
        return bool(CalendarEventRepository(db_engine).overlapping(now))
    except Exception:
        logger.exception("Không đọc được lịch họp, coi như không họp")
        return False
