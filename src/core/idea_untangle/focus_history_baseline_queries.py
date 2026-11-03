"""Truy vấn lịch sử focus/task làm baseline cho nudge thích nghi (phase 04). Chỉ đọc, ngày theo giờ máy."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy.engine import Engine
from sqlalchemy import func
from sqlmodel import Session, select

from src.config import settings
from src.core.models import FocusSession, Task, _local_date_iso


def _sessions_desc(engine: Engine, limit: int = 0) -> List[FocusSession]:
    with Session(engine) as s:
        stmt = select(FocusSession).order_by(FocusSession.started_at.desc())
        if limit:
            stmt = stmt.limit(limit)
        return list(s.exec(stmt).all())


def task_focus_minutes_total(engine: Engine, task_id: str) -> int:
    with Session(engine) as s:
        return int(sum(s.exec(select(FocusSession.actual_minutes).where(FocusSession.task_id == task_id)).all()))


def consecutive_sessions_on_task_today(engine: Engine, task_id: str) -> int:
    """Số phiên focus LIÊN TIẾP gần nhất (hôm nay) cùng task_id; gặp phiên task khác/ngày khác là dừng."""
    today = _local_date_iso(datetime.now(timezone.utc))
    count = 0
    for row in _sessions_desc(engine, 50):
        if row.task_id != task_id or _local_date_iso(row.started_at) != today:
            break
        count += 1
    return count


def historical_overrun_ratios(engine: Engine, limit: int = 30) -> List[float]:
    """Task đã xong có phiên focus: tổng phút focus / (ước lượng × phút pomodoro). >1 = làm lố.

    1 truy vấn gộp (JOIN + GROUP BY) cho `limit` task xong gần nhất — chạy trên UI thread nên không được N+1."""
    pomo = max(1, int(settings.default_pomodoro_mins))
    minutes = func.sum(FocusSession.actual_minutes)
    stmt = (select(Task.estimated_pomodoros, minutes)
            .join(FocusSession, FocusSession.task_id == Task.id)
            .where(Task.status == "done")
            .group_by(Task.id)
            .having(minutes > 0)
            .order_by(Task.updated_at.desc())
            .limit(limit))
    with Session(engine) as s:
        return [int(mins) / (max(1, est) * pomo) for est, mins in s.exec(stmt).all()]


def daily_same_task_session_counts(engine: Engine, days: int = 30) -> List[int]:
    """Mỗi cặp (ngày, task) trong `days` ngày gần nhất → số phiên focus của task đó trong ngày.

    Lọc mốc thời gian ngay trong SQL và chỉ đọc 2 cột, để chi phí không tăng theo toàn bộ lịch sử."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(FocusSession.started_at, FocusSession.task_id).where(
        FocusSession.started_at >= cutoff, FocusSession.task_id.is_not(None))
    counts: Counter = Counter()
    with Session(engine) as s:
        for started, task_id in s.exec(stmt).all():
            counts[(_local_date_iso(started), task_id)] += 1
    return list(counts.values())


def distraction_rate_baseline(engine: Engine, limit: int = 30) -> List[float]:
    """Xao nhãng trên mỗi 25 phút, theo từng phiên gần đây có actual_minutes > 0."""
    return [r.distraction_count * 25.0 / r.actual_minutes
            for r in _sessions_desc(engine, limit * 2) if r.actual_minutes > 0][:limit]
