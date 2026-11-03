"""Tín hiệu kẹt riêng của engine coach: sai lặp lại cùng câu/chủ đề + gợi ý loại vấn đề từ hoạt động gần nhất."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Tuple

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from src.core.idea_untangle.untangle_problem_kinds_by_engine import DEFAULT_KIND
from src.engines.coach.coach_data_models import Attempt, QuizItem, WritingSubmission

WRONG_LIMIT = 3
RECENT_ACTIVITY_MINS = 60          # hoạt động "gần đây" để đoán loại vấn đề khi kẹt do thời gian

# Loại câu coach → loại vấn đề Gỡ Rối (step = bài toán nhiều bước; mcq/short = hiểu khái niệm)
_KIND_BY_ITEM_TYPE = {"step": "math_problem", "mcq": "concept", "short": "concept"}


@dataclass(frozen=True)
class CoachSignals:
    wrong_streak: bool = False
    kind: str = DEFAULT_KIND


def wrong_streak_kind(rows: Iterable[Tuple[str, str, str, bool]], limit: int = WRONG_LIMIT) -> Optional[str]:
    """rows = (item_id, topic, item_type, correct). ≥ limit lần sai cùng câu HOẶC cùng chủ đề → loại vấn đề, else None.

    Cùng câu ưu tiên hơn cùng chủ đề; loại lấy từ item_type của lần sai gần nhất thuộc nhóm đó (rows theo thời gian).
    """
    by_item: Counter = Counter()
    by_topic: Counter = Counter()
    last_type_item: dict = {}
    last_type_topic: dict = {}
    for item_id, topic, item_type, correct in rows:
        if correct:
            continue
        by_item[item_id] += 1
        last_type_item[item_id] = item_type
        if topic.strip():
            by_topic[topic] += 1
            last_type_topic[topic] = item_type
    for counter, types in ((by_item, last_type_item), (by_topic, last_type_topic)):
        for key, n in counter.items():
            if n >= limit:
                return _KIND_BY_ITEM_TYPE.get(types[key], DEFAULT_KIND)
    return None


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def coach_signals(engine: Engine, module_id: str, now: datetime) -> CoachSignals:
    """Đọc Attempt/WritingSubmission của module trong ngày (giờ máy) → tín hiệu kẹt. Lỗi DB để caller bắt."""
    local_midnight = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = local_midnight.astimezone(timezone.utc)
    recent_from = _aware(now) - timedelta(minutes=RECENT_ACTIVITY_MINS)
    with Session(engine) as s:
        rows = s.exec(
            select(Attempt.item_id, QuizItem.topic, QuizItem.type, Attempt.correct, Attempt.answered_at)
            .join(QuizItem, QuizItem.id == Attempt.item_id)
            .where(Attempt.module_id == module_id, Attempt.answered_at >= day_start)
            .order_by(Attempt.answered_at)
        ).all()
        kind = wrong_streak_kind((r[0], r[1], r[2], r[3]) for r in rows)
        if kind:
            return CoachSignals(True, kind)
        last_draft = s.exec(select(WritingSubmission.created_at).where(
            WritingSubmission.module_id == module_id, WritingSubmission.created_at >= recent_from)).first()
    # Kẹt vì thời gian: bài viết gần nhất → cấu trúc bài viết; không thì câu step gần nhất → bài toán
    if last_draft is not None:
        return CoachSignals(False, "essay_structure")
    recent = [r for r in rows if _aware(r[4]) >= recent_from]
    if recent:
        return CoachSignals(False, _KIND_BY_ITEM_TYPE.get(recent[-1][2], DEFAULT_KIND))
    return CoachSignals()
