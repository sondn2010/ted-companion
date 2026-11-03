"""Leitner 6 hộp (0..5) thuần hàm; khoảng cách ngày do policy.leitner_days quyết định."""

from datetime import datetime, timedelta
from typing import NamedTuple, Sequence

from src.engines.coach.utc_aware_datetime_type import require_aware

MAX_BOX = 5


class ReviewOutcome(NamedTuple):
    box: int
    lapses: int
    due_at: datetime


def due_after_box(box: int, now: datetime, leitner_days: Sequence[float]) -> datetime:
    return require_aware(now) + timedelta(days=leitner_days[box])


def next_review(box: int, lapses: int, correct: bool, now: datetime, leitner_days: Sequence[float]) -> ReviewOutcome:
    """Đúng → lên 1 hộp (tối đa 5); sai → hộp 0 và lapses+1. due_at = now + leitner_days[hộp mới]."""
    if len(leitner_days) != MAX_BOX + 1:
        raise ValueError("leitner_days phải có đúng 6 giá trị")
    if correct:
        new_box, new_lapses = min(box + 1, MAX_BOX), lapses
    else:
        new_box, new_lapses = 0, lapses + 1
    return ReviewOutcome(new_box, new_lapses, due_after_box(new_box, now, leitner_days))
