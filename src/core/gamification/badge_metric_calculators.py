"""Registry metric cho badge: METRICS[name](WindowData) -> float. Thêm metric = thêm 1 dòng (catalog JSON chỉ tham chiếu tên)."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

from src.core.gamification.day_signals_collector import DaySignals
from src.core.gamification.level_progression_engine import MIN_DAILY_XP, WeekProgress
from src.core.gamification.wellbeing_stat_formulas import DayStats


# Metric sức khỏe/năng lượng theo NGÀY chỉ có nghĩa khi ngày đã kết thúc: giữa buổi sáng khoảng trống đêm qua
# (07:00–giờ mở app) là "vắng mặt" còn app_on rất nhỏ nên Health ≈ 90 → huy hiệu mở mỗi sáng. Chỉ chấm ngày đã qua.
FINISHED_DAY_ONLY_METRICS = frozenset({"away_minutes", "health", "energy"})


@dataclass
class WindowData:
    """Dữ liệu của một cửa sổ: 1 ngày, 1 tuần, hoặc trọn đời (totals != None, days rỗng)."""
    days: List[DaySignals] = field(default_factory=list)
    stats: List[DayStats] = field(default_factory=list)       # chỉ các ngày có hoạt động
    progress: WeekProgress = field(default_factory=WeekProgress)
    prev_week_xp: int = 0
    prev_final_level: Optional[int] = None
    totals: Optional[Dict[str, float]] = None


def longest_streak(daily_xp: Dict[date, int], min_xp: int = MIN_DAILY_XP) -> int:
    """Số ngày liên tiếp dài nhất có xp >= min_xp."""
    best = run = 0
    prev: Optional[date] = None
    for d in sorted(k for k, v in daily_xp.items() if v >= min_xp):
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        best, prev = max(best, run), d
    return best


def _additive(metric: str, day_field: str) -> Callable[[WindowData], float]:
    def calc(w: WindowData) -> float:
        if w.totals is not None:
            return float(w.totals.get(metric, 0))
        return float(sum(getattr(d, day_field) for d in w.days))
    return calc


def _stat_mean(attr: str) -> Callable[[WindowData], float]:
    return lambda w: sum(getattr(s, attr) for s in w.stats) / len(w.stats) if w.stats else 0.0


def _stat_max(attr: str) -> Callable[[WindowData], float]:
    return lambda w: float(max((getattr(s, attr) for s in w.stats), default=0))


def _study_days(w: WindowData) -> float:
    if w.totals is not None:
        return float(w.totals.get("study_days", 0))
    return float(sum(1 for d in w.days if d.quiz_answered + d.agenda_done + d.writing_graded > 0))


def _active_days(w: WindowData) -> float:
    if w.totals is not None:
        return float(w.totals.get("active_days", 0))
    return float(sum(1 for d in w.days if d.xp_day >= MIN_DAILY_XP))


def _best_streak(w: WindowData) -> float:
    if w.totals is not None:
        return float(w.totals.get("best_streak_days", 0))
    best = run = 0
    for d in w.days:  # w.days đã sắp theo ngày liên tiếp
        run = run + 1 if d.xp_day >= MIN_DAILY_XP else 0
        best = max(best, run)
    return float(best)


def _quiz_accuracy_pct(w: WindowData) -> float:
    answered, correct = METRICS["quiz_answered"](w), METRICS["quiz_correct"](w)
    return 100.0 * correct / answered if answered > 0 else 0.0


def _xp_total(w: WindowData) -> float:
    return float(w.totals.get("xp_total", 0)) if w.totals is not None else float(sum(d.xp_day for d in w.days))


def _xp_growth_pct(w: WindowData) -> float:
    if w.prev_week_xp <= 0:
        return 0.0
    return 100.0 * (_xp_total(w) - w.prev_week_xp) / w.prev_week_xp


def _level_growth(w: WindowData) -> float:
    return 0.0 if w.prev_final_level is None else float(w.progress.level - w.prev_final_level)


METRICS: Dict[str, Callable[[WindowData], float]] = {
    "focus_minutes": _additive("focus_minutes", "focus_minutes"),
    "focus_sessions": _additive("focus_sessions", "sessions"),
    "clean_sessions": _additive("clean_sessions", "clean_sessions"),
    "tasks_done": _additive("tasks_done", "tasks_done"),
    "quiz_answered": _additive("quiz_answered", "quiz_answered"),
    "quiz_correct": _additive("quiz_correct", "quiz_correct"),
    "agenda_done": _additive("agenda_done", "agenda_done"),
    "writing_graded": _additive("writing_graded", "writing_graded"),
    "outings": _additive("outings", "outings"),
    "breaks_taken": _additive("breaks_taken", "breaks"),
    "meeting_minutes": _additive("meeting_minutes", "work_meeting_minutes"),
    "meetings_done": _additive("meetings_done", "meeting_sessions"),          # phiên Họp/Học nhóm do Ted ghi
    "teacher_sessions": _additive("teacher_sessions", "teacher_sessions"),    # phiên "Học với thầy cô"
    "away_minutes": _additive("away_minutes", "away_minutes"),
    "quiz_accuracy_pct": _quiz_accuracy_pct,
    "study_days": _study_days,
    "active_days": _active_days,
    "best_streak_days": _best_streak,
    "energy": _stat_max("energy"),
    "health": _stat_max("health"),
    "health_avg": _stat_mean("health"),
    "screen_load_avg": _stat_mean("screen_load"),
    "engagement_avg": _stat_mean("engagement"),
    "energy_avg": _stat_mean("energy"),
    "peak_level": lambda w: float(w.progress.peak_level),
    "comeback": lambda w: 1.0 if w.progress.demoted_then_recovered else 0.0,
    "xp_total": _xp_total,
    "xp_growth_pct": _xp_growth_pct,
    "level_growth": _level_growth,
    "prev_week_xp": lambda w: float(w.prev_week_xp),
}
