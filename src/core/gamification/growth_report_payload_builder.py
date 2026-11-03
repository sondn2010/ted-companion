"""Dựng payload báo cáo tăng trưởng gửi Hermes. Hai biểu mẫu chung một phép gom số (growth_report_aggregation):

- `learning`: profile coach — chỉ học tập (data/learning, đếm quiz/agenda/writing, XP coach, huy hiệu học tập).
- `general`: profile Work + Ted — mọi chỉ số, level, tất cả huy hiệu, kèm khối `wellbeing` TÁCH RIÊNG
  (sau này profile sức khỏe chỉ cần đúng khối này: xem `wellbeing_block_of_*`).
Chỉ số nguyên đã tổng hợp + id huy hiệu; không tiêu đề task, câu hỏi, đáp án, tiêu đề lịch.
Họp/Học nhóm: chỉ SỐ ĐẾM + phút (general: meetings/meeting_minutes; learning: study_meetings/study_meeting_minutes
= Học nhóm + Học với thầy cô). KHÔNG BAO GIỜ gửi chủ đề (topic) — riêng tư.
"""

from typing import Any, Dict

from src.core.gamification.growth_report_aggregation import DayAggregate, WeekAggregate

LEARNING = "learning"
GENERAL = "general"
REPORT_KINDS = (LEARNING, GENERAL)
STUDY_COUNTS = ("quiz_answered", "quiz_correct", "agenda_done", "writing_graded")


def meeting_counts_of(days, learning: bool) -> Dict[str, int]:
    """Số phiên + phút họp của các ngày (learning: chỉ Học nhóm / Học với thầy cô)."""
    if learning:
        return {"study_meetings": sum(d.study_meeting_sessions for d in days),
                "study_meeting_minutes": sum(d.study_meeting_minutes for d in days)}
    return {"meetings": sum(d.meeting_sessions for d in days),
            "meeting_minutes": sum(d.meeting_session_minutes for d in days)}


def wellbeing_block_of_day(agg: DayAggregate) -> Dict[str, int]:
    s, st = agg.signals, agg.stats
    return {"health": st.health, "engagement": st.engagement, "screen_load": st.screen_load,
            "app_on_minutes": s.app_on_minutes, "away_minutes": s.away_minutes, "breaks": s.breaks,
            "outings": s.outings, "late_night_minutes": s.late_night_minutes,
            "micro_breaks": s.micro_breaks, "micro_water": s.micro_water, "micro_move": s.micro_move}


def wellbeing_block_of_week(agg: WeekAggregate) -> Dict[str, int]:
    days, avg = agg.ctx.days, agg.stats_end
    return {"health": avg.get("health") or 0, "engagement": avg.get("engagement") or 0,
            "screen_load": avg.get("screen_load") or 0,
            "app_on_minutes": sum(d.app_on_minutes for d in days), "away_minutes": sum(d.away_minutes for d in days),
            "breaks": sum(d.breaks for d in days), "outings": sum(d.outings for d in days),
            "late_night_minutes": sum(d.late_night_minutes for d in days),
            "micro_breaks": sum(d.micro_breaks for d in days), "micro_water": sum(d.micro_water for d in days),
            "micro_move": sum(d.micro_move for d in days)}


def _stats(values: Dict[str, Any], names: tuple) -> Dict[str, int]:
    """Chỉ giữ chỉ số có giá trị (learning=None khi không có coach → bỏ khóa)."""
    return {n: int(values[n]) for n in names if values.get(n) is not None}


def build_daily_payload(report_kind: str, learner: str, agg: DayAggregate) -> Dict[str, Any]:
    s = agg.signals
    base = {"kind": "daily", "report_kind": report_kind, "date": agg.day.isoformat(), "learner": learner}
    if report_kind == LEARNING:
        return {**base, "stats": _stats(agg.stats.as_dict(), ("data", "learning")), "coach_xp": agg.coach_xp,
                "counts": {**{f: getattr(s, f) for f in STUDY_COUNTS}, **meeting_counts_of([s], True)},
                "badges_new": agg.learning_badges_new, "badges_total": agg.learning_badges_total}
    return {**base, "level": agg.level, "pct": agg.pct, "xp_day": s.xp_day, "decayed": agg.decayed,
            "stats": _stats(agg.stats.as_dict(), ("energy", "data", "learning")),
            "counts": {"focus_minutes": s.focus_minutes, "focus_sessions": s.sessions, "tasks_done": s.tasks_done,
                       **{f: getattr(s, f) for f in STUDY_COUNTS}, **meeting_counts_of([s], False)},
            "badges_new": agg.badges_new, "badges_total": agg.badges_total,
            "wellbeing": wellbeing_block_of_day(agg)}


def build_weekly_payload(report_kind: str, learner: str, agg: WeekAggregate) -> Dict[str, Any]:
    days = agg.ctx.days
    base = {"kind": "weekly", "report_kind": report_kind, "week_start": agg.week_start.isoformat(),
            "learner": learner}
    if report_kind == LEARNING:
        study_days = sum(1 for d in days if d.quiz_answered or d.agenda_done or d.writing_graded)
        return {**base, "stats_end": _stats(agg.stats_end, ("data", "learning")), "coach_xp": agg.coach_xp,
                "counts": {**{f: sum(getattr(d, f) for d in days) for f in STUDY_COUNTS},
                           **meeting_counts_of(days, True)},
                "active_days": study_days, "badges": agg.learning_badges, "badges_total": agg.learning_badges_total}
    p = agg.ctx.progress
    return {**base, "final_level": p.level, "final_pct": p.pct, "peak_level": p.peak_level, "xp_earned": agg.xp_earned,
            "active_days": p.active_days, "decay_days": p.decay_days,
            "stats_end": _stats(agg.stats_end, ("energy", "data", "learning")),
            "counts": meeting_counts_of(days, False),
            "badges": agg.badges, "badges_total": agg.badges_total, "wellbeing": wellbeing_block_of_week(agg)}
