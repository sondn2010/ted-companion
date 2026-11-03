"""Tổng trọn đời cho badge window=lifetime (dict tên metric → giá trị), tính từ ledger + FocusSession + wellbeing."""

from datetime import date
from typing import Dict

from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

from src.core.gamification.badge_metric_calculators import longest_streak
from src.core.gamification.gamification_table_models import DailyWellbeing
from src.core.gamification.level_progression_engine import MIN_DAILY_XP
from src.core.gamification.xp_ledger_repository import XpLedgerRepository
from src.core.meeting_mode.meeting_session_table_model_and_repository import KIND_TEACHER, MeetingSession
from src.core.models import FocusSession


def build_lifetime_totals(engine: Engine, ledger: XpLedgerRepository, today: date) -> Dict[str, float]:
    counts = ledger.lifetime_counts()
    MeetingSession.__table__.create(engine, checkfirst=True)   # DB test/cũ có thể chưa có bảng họp
    first = ledger.first_event_date()
    daily = ledger.daily_totals(first, today) if first else {}
    scope = getattr(ledger, "scope", None)   # learning-only: không tính focus/outing (công việc, đời sống)
    with Session(engine) as s:
        minutes, sessions = s.exec(select(func.coalesce(func.sum(FocusSession.actual_minutes), 0),
                                          func.count(FocusSession.id)).where(FocusSession.actual_minutes > 0)).one()
        clean = s.exec(select(func.count(FocusSession.id)).where(
            FocusSession.actual_minutes > 0, FocusSession.distraction_count == 0)).one()
        outings = s.exec(select(func.coalesce(func.sum(DailyWellbeing.outings), 0))).one()
        meetings = s.exec(select(func.count(MeetingSession.id)).where(MeetingSession.actual_minutes > 0)).one()
        teacher = s.exec(select(func.count(MeetingSession.id)).where(
            MeetingSession.actual_minutes > 0, MeetingSession.kind == KIND_TEACHER)).one()
    if scope:
        minutes = sessions = clean = outings = 0
        if not scope.include_meetings:
            meetings = teacher = 0
    return {
        "focus_minutes": float(minutes), "focus_sessions": float(sessions), "clean_sessions": float(clean),
        "tasks_done": float(max(0, counts["task_done"] - counts["task_undone"])),
        "quiz_answered": float(counts["quiz_answered"]), "quiz_correct": float(counts["quiz_correct"]),
        "agenda_done": float(counts["agenda_done"]), "writing_graded": float(counts["writing_graded"]),
        "outings": float(outings), "meetings_done": float(meetings), "teacher_sessions": float(teacher),
        "xp_total": float(sum(daily.values())),
        "best_streak_days": float(longest_streak(daily)),
        "active_days": float(sum(1 for v in daily.values() if v >= MIN_DAILY_XP)),
    }
