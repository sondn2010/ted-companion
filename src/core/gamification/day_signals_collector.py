"""Gom tín hiệu 1 ngày local (focus, XP ledger, wellbeing, lịch) thành DaySignals bất biến cho công thức chỉ số + badge."""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Tuple

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from src.config import settings
from src.core.gamification.gamification_table_models import XpEvent
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.xp_ledger_repository import XpLedgerRepository
from src.core.gamification.day_calendar_and_meeting_minutes import (   # noqa: F401  (is_personal_event: re-export cho test)
    calendar_minutes, is_personal_event, meeting_intervals, meeting_rows, meeting_signals)
from src.core.models import FocusSession

logger = logging.getLogger("ted")

CHAIN_MAX_GAP_MINUTES = 5          # hở < 5 phút (và không có nghỉ) = vẫn cùng một chuỗi tập trung
STUDY_KINDS = ("quiz_answered", "agenda_done", "writing_graded")
MIN_ANSWERS_FOR_ACCURACY = 5


@dataclass(frozen=True)
class DaySignals:
    focus_minutes: int = 0
    sessions: int = 0
    clean_sessions: int = 0
    focus_chain_max: int = 0
    tasks_done: int = 0
    quiz_answered: int = 0
    quiz_correct: int = 0
    quiz_wrong: int = 0
    agenda_done: int = 0
    writing_graded: int = 0
    xp_day: int = 0
    xp_7d_avg: float = 0.0
    study_days_7d: int = 0
    accuracy_7d: float = 0.5
    app_on_minutes: int = 0
    away_minutes: int = 0
    late_night_minutes: int = 0
    breaks: int = 0
    break_minutes: int = 0
    outings: int = 0
    work_meeting_minutes: int = 0
    personal_event_minutes: int = 0
    has_coach: bool = False
    micro_breaks: int = 0
    micro_water: int = 0
    micro_move: int = 0
    meeting_sessions: int = 0           # số phiên Họp/Học nhóm trong ngày (mọi loại)
    meeting_session_minutes: int = 0    # tổng phút các phiên đó (khác work_meeting_minutes = họp theo lịch Google)
    teacher_sessions: int = 0           # số phiên "Học với thầy cô"
    study_meeting_sessions: int = 0     # Học nhóm + Học với thầy cô (báo cáo learning của coach)
    study_meeting_minutes: int = 0


def _utc_bounds(day: date) -> Tuple[datetime, datetime]:
    """[00:00 local, 00:00 hôm sau) → UTC aware (sqlmodel bắt buộc datetime có tzinfo)."""
    def conv(d: date) -> datetime:
        return datetime.combine(d, time.min).astimezone(timezone.utc)
    return conv(day), conv(day + timedelta(days=1))


def _aware(dt: datetime) -> datetime:
    """SQLite có thể trả naive (UTC) → gắn tzinfo UTC để so sánh an toàn."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def longest_focus_chain(sessions: List[Tuple[datetime, datetime, int]], break_times: List[datetime]) -> int:
    """sessions = (start, end, phút) đã sắp theo start. Chuỗi = hở < 5 phút và không có lần nghỉ chen giữa; trả tổng phút chuỗi dài nhất."""
    best = current = 0
    prev_end = None
    for start, end, minutes in sessions:
        continues = (prev_end is not None
                     and start - prev_end < timedelta(minutes=CHAIN_MAX_GAP_MINUTES)
                     and not any(prev_end <= b <= start for b in break_times))
        current = current + minutes if continues else minutes
        best = max(best, current)
        prev_end = max(end, prev_end) if prev_end else end
    return best


def collect_day_signals(engine: Engine, ledger: XpLedgerRepository, wellbeing: WellbeingDailyRepository,
                        day: date) -> DaySignals:
    lo, hi = _utc_bounds(day)
    scope = getattr(ledger, "scope", None)   # ScopedXpLedger (báo cáo learning): chỉ dữ liệu coach của 1 learner
    with Session(engine) as s:
        # learning-only: bỏ focus (tín hiệu công việc) để chỉ số `data` không lẫn việc/tập trung
        rows = [] if scope else s.exec(select(FocusSession).where(
            FocusSession.started_at >= lo, FocusSession.started_at < hi, FocusSession.actual_minutes > 0)
            .order_by(FocusSession.started_at)).all()
        break_times = [_aware(t) for t in s.exec(select(XpEvent.ts).where(
            XpEvent.kind == "break_taken", XpEvent.ts >= lo, XpEvent.ts < hi)).all()]
        coach_q = select(XpEvent.id).where(XpEvent.kind.in_(STUDY_KINDS), XpEvent.local_date <= day.isoformat())
        if scope:
            coach_q = coach_q.where(XpEvent.source_module.in_(sorted(scope.modules)))
        has_coach = s.exec(coach_q.limit(1)).first() is not None
    sessions = [(_aware(r.started_at), _aware(r.ended_at or r.started_at + timedelta(minutes=r.actual_minutes)),
                 r.actual_minutes)
                for r in rows]

    week_from = day - timedelta(days=6)
    per_day = ledger.kind_counts_by_day(week_from, day)
    totals = ledger.daily_totals(week_from, day)
    today_counts = per_day.get(day, {})
    study_days = sum(1 for c in per_day.values() if any(c.get(k, 0) for k in STUDY_KINDS))
    answered_7d = sum(c.get("quiz_answered", 0) for c in per_day.values())
    correct_7d = sum(c.get("quiz_correct", 0) for c in per_day.values())
    accuracy = min(1.0, correct_7d / answered_7d) if answered_7d >= MIN_ANSWERS_FOR_ACCURACY else 0.5

    answered, correct = today_counts.get("quiz_answered", 0), today_counts.get("quiz_correct", 0)
    wb = wellbeing.get(day)
    # phiên Họp/Học nhóm: learning-only chỉ lấy khi không có learner khác (phiên không gắn module)
    meetings = [] if scope and not scope.include_meetings else meeting_rows(engine, lo, hi)
    # họp trùng giữa lịch và phiên Ted chỉ tính 1 lần (ưu tiên phiên Ted)
    work_min, personal_min = (0, 0) if scope else calendar_minutes(engine, day, meeting_intervals(meetings))
    return DaySignals(
        focus_minutes=sum(m for _, _, m in sessions), sessions=len(sessions),
        clean_sessions=sum(1 for r in rows if r.distraction_count == 0),
        focus_chain_max=longest_focus_chain(sessions, break_times),
        tasks_done=max(0, today_counts.get("task_done", 0) - today_counts.get("task_undone", 0)),
        quiz_answered=answered, quiz_correct=correct, quiz_wrong=max(0, answered - correct),
        agenda_done=today_counts.get("agenda_done", 0), writing_graded=today_counts.get("writing_graded", 0),
        xp_day=totals.get(day, 0), xp_7d_avg=sum(totals.values()) / 7, study_days_7d=study_days,
        accuracy_7d=accuracy, app_on_minutes=wb.app_on_minutes, away_minutes=wb.away_minutes,
        late_night_minutes=wb.late_night_minutes, breaks=wb.breaks_taken,
        break_minutes=wb.breaks_taken * settings.default_break_mins, outings=wb.outings,
        work_meeting_minutes=work_min, personal_event_minutes=personal_min, has_coach=has_coach,
        micro_breaks=wb.micro_breaks_done, micro_water=wb.micro_water_done, micro_move=wb.micro_move_done,
        **(meeting_signals(meetings) if meetings else {}))
