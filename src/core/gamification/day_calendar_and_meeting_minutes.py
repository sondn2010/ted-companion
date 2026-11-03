"""Phút lịch (họp công việc / sự kiện cá nhân) và phiên Họp/Học nhóm của 1 ngày local cho DaySignals.

Một cuộc họp có thể vừa là sự kiện lịch vừa là phiên Ted: phần lịch trùng với phiên Ted chỉ tính 1 lần
(ưu tiên phiên Ted, vì nó có điểm Gắn kết riêng) -> trừ phần trùng khỏi phút lịch.
"""

import logging
from datetime import datetime, time, timedelta, timezone
from typing import List, Tuple

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from src.core.meeting_mode.meeting_session_table_model_and_repository import (
    KIND_TEACHER, STUDY_MEETING_KINDS, MeetingSession)

logger = logging.getLogger("ted")

PERSONAL_START_HOUR, PERSONAL_END_HOUR = 8, 18
Interval = Tuple[datetime, datetime]   # giờ local, naive


def is_personal_event(start_local: datetime, end_local: datetime, all_day: bool) -> bool:
    """Cả ngày, Thứ 7/CN, hoặc nằm hoàn toàn ngoài 08:00–18:00 → sự kiện cá nhân."""
    if all_day or start_local.weekday() >= 5:
        return True
    open_at = datetime.combine(start_local.date(), time(PERSONAL_START_HOUR))
    close_at = datetime.combine(start_local.date(), time(PERSONAL_END_HOUR))
    return end_local <= open_at or start_local >= close_at


def meeting_rows(engine: Engine, lo: datetime, hi: datetime) -> List[MeetingSession]:
    """Phiên Họp/Học nhóm bắt đầu trong [lo, hi) đã kết thúc (>= 1 phút). Lỗi bảng -> rỗng."""
    try:
        MeetingSession.__table__.create(engine, checkfirst=True)
        with Session(engine) as s:
            return list(s.exec(select(MeetingSession).where(
                MeetingSession.started_at >= lo, MeetingSession.started_at < hi, MeetingSession.actual_minutes > 0)).all())
    except Exception:  # noqa: BLE001 - không làm hỏng chỉ số
        logger.warning("Không đọc được phiên họp cho gamification", exc_info=True)
        return []


def meeting_signals(rows: List[MeetingSession]) -> dict:
    study = [r for r in rows if r.kind in STUDY_MEETING_KINDS]
    return dict(meeting_sessions=len(rows), meeting_session_minutes=sum(r.actual_minutes for r in rows),
                teacher_sessions=sum(1 for r in rows if r.kind == KIND_TEACHER),
                study_meeting_sessions=len(study), study_meeting_minutes=sum(r.actual_minutes for r in study))


def _merged(intervals: List[Interval]) -> List[Interval]:
    out: List[Interval] = []
    for start, end in sorted(intervals):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def meeting_intervals(rows: List[MeetingSession]) -> List[Interval]:
    """Khoảng [bắt đầu, bắt đầu + actual_minutes] của các phiên Ted, đã gộp phần chồng nhau (giờ local naive)."""
    spans = []
    for r in rows:
        started = r.started_at if r.started_at.tzinfo else r.started_at.replace(tzinfo=timezone.utc)
        start = started.astimezone().replace(tzinfo=None)
        spans.append((start, start + timedelta(minutes=r.actual_minutes)))
    return _merged(spans)


def overlap_minutes(start: datetime, end: datetime, busy: List[Interval]) -> int:
    """Số phút của [start, end] nằm trong các khoảng `busy` (đã gộp, không chồng nhau)."""
    total = sum(max(0.0, (min(end, b) - max(start, a)).total_seconds()) for a, b in busy)
    return int(total // 60)


def calendar_minutes(engine: Engine, day, busy: List[Interval]) -> Tuple[int, int]:
    """(phút họp công việc, phút sự kiện cá nhân) của ngày, đã trừ phần trùng phiên Ted (`busy`).
    Lỗi lịch -> (0, 0), không làm hỏng chỉ số."""
    try:
        from src.engines.work.calendar_event_cache_model_and_repository import (
            CalendarEventRepository, event_end)
        lo = datetime.combine(day, time.min).astimezone()
        hi = datetime.combine(day + timedelta(days=1), time.min).astimezone()
        work = personal = 0
        for ev in CalendarEventRepository(engine).between(lo.astimezone(timezone.utc), hi.astimezone(timezone.utc)):
            s, e = ev.start_at.astimezone().replace(tzinfo=None), event_end(ev).astimezone().replace(tzinfo=None)
            minutes = max(0, min(1440, int((e - s).total_seconds() // 60)))
            if not ev.all_day:   # sự kiện cả ngày không có giờ cụ thể -> không trùng được phiên Ted
                minutes = max(0, minutes - overlap_minutes(s, e, busy))
            if is_personal_event(s, e, ev.all_day):
                personal += minutes
            elif not ev.all_day:
                work += minutes
        return work, personal
    except Exception:  # noqa: BLE001 - lịch là nguồn phụ
        logger.warning("Không đọc được lịch cho gamification", exc_info=True)
        return 0, 0
