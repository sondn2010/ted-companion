"""Cổng "đang họp": Ted không nói to (chỉ bubble) khi lịch cache cho thấy đang trong cuộc họp."""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("ted")


def is_in_meeting(calendar_repo, now_utc: Optional[datetime] = None) -> bool:
    if calendar_repo is None:
        return False
    try:
        return bool(calendar_repo.overlapping(now_utc or datetime.now(timezone.utc), 0))
    except Exception:
        logger.exception("Không kiểm tra được đang họp, coi như rảnh")
        return False
