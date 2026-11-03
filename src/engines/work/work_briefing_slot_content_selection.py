"""Chọn nội dung briefing theo slot (thuần DB/lọc): việc mở xếp theo ô Eisenhower, họp sáng/chiều."""

from datetime import date, datetime, time

from sqlmodel import Session, select

from src.core.models import Task
from src.engines.work.work_briefing_due_window import MIDDAY

MAX_TASKS = 5
OPEN_STATUSES = ("todo", "in_progress")
_UNSORTED_RANK = 5  # Unsorted xếp sau Q4


def open_task_titles_for_slot(db_engine, today: date, slot: str) -> list[str]:
    """Sáng: việc hôm nay (trừ ý tưởng đã đỗ) + mọi việc/ý tưởng Q1/Q2, xếp Q1,Q2,Q3,Q4,Unsorted.
    Trưa: chỉ việc mở thuộc Q1/Q2 (kể cả ý tưởng đã đỗ)."""
    with Session(db_engine) as session:
        rows = session.exec(select(Task).where(Task.status.in_(OPEN_STATUSES))).all()

    def wanted(task: Task) -> bool:
        if task.quadrant in (1, 2):
            return True
        return slot != MIDDAY and task.scheduled_date == today.isoformat() and task.category != "parked_idea"

    picked = sorted(
        (t for t in rows if wanted(t)),
        key=lambda t: (t.quadrant or _UNSORTED_RANK, t.matrix_order, t.updated_at),
    )
    return [t.title for t in picked[:MAX_TASKS]]


def events_for_slot(events: list[tuple[datetime, str]], slot: str, boundary: time) -> list[tuple[datetime, str]]:
    """Sáng: họp bắt đầu trước `boundary` (12:00); trưa: từ `boundary` trở đi. Giờ theo local."""
    afternoon = slot == MIDDAY
    return [(s, t) for s, t in events if (s.astimezone().time().replace(second=0, microsecond=0) >= boundary) == afternoon]
