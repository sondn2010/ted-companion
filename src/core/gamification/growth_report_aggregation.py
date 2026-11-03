"""Gom số liệu 1 ngày / 1 tuần cho báo cáo tăng trưởng gửi Hermes (dùng chung cho báo cáo learning và general).

Chỉ trả số đã tổng hợp + id huy hiệu; không đụng tiêu đề task/câu hỏi/đáp án.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, FrozenSet, List, Optional, Set

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from src.core.gamification.badge_catalog_loader import CatalogError, load_badge_catalog
from src.core.gamification.badge_unlock_repository import BadgeUnlockRepository
from src.core.gamification.day_signals_collector import DaySignals, collect_day_signals
from src.core.gamification.gamification_table_models import XpEvent
from src.core.gamification.learner_scope_ledger_and_badges import scoped_learning_unlocks
from src.core.gamification.level_progression_engine import MIN_DAILY_XP, replay_week, week_start_of
from src.core.gamification.week_context_builder import WeekContext, build_week_context, running_stats
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.wellbeing_stat_formulas import DayStats, has_stat_activity
from src.core.gamification.xp_ledger_repository import XpLedgerRepository, local_date_of

LEARNING_BADGE_CATEGORIES = ("learning", "writing")   # nhóm huy hiệu thuộc báo cáo "học tập"
STUDY_COUNT_FIELDS = ("quiz_answered", "quiz_correct", "agenda_done", "writing_graded", "study_meeting_sessions")


@dataclass(frozen=True)
class GrowthSources:
    engine: Engine
    ledger: XpLedgerRepository
    wellbeing: WellbeingDailyRepository
    unlocks: BadgeUnlockRepository


@dataclass(frozen=True)
class DayAggregate:
    day: date
    signals: DaySignals
    stats: DayStats
    level: int
    pct: float
    decayed: bool
    coach_xp: int
    badges_new: List[str]
    badges_total: int
    learning_badges_new: List[str]
    learning_badges_total: int


@dataclass(frozen=True)
class WeekAggregate:
    week_start: date
    ctx: WeekContext
    xp_earned: int
    coach_xp: int
    stats_end: Dict[str, Optional[int]]
    badges: List[str]
    badges_total: int
    learning_badges: List[str]
    learning_badges_total: int


def learning_badge_ids() -> Set[str]:
    """Id huy hiệu thuộc nhóm học tập; catalog hỏng → rỗng (báo cáo vẫn gửi, chỉ không kèm huy hiệu)."""
    try:
        return {b.id for b in load_badge_catalog().badges if b.category in LEARNING_BADGE_CATEGORIES}
    except CatalogError:
        return set()


def coach_xp_by_day(engine: Engine, start: date, end: date,
                    modules: Optional[FrozenSet[str]] = None) -> Dict[date, int]:
    """XP từ module coach mỗi ngày (kể cả âm) — phần XP duy nhất lộ ra ở báo cáo learning.
    `modules` != None → chỉ các module của learner đích (con cái khác profile không thấy nhau)."""
    out: Dict[date, int] = {}
    query = select(XpEvent.local_date, XpEvent.xp).where(
        XpEvent.engine == "coach", XpEvent.local_date >= start.isoformat(), XpEvent.local_date <= end.isoformat())
    if modules is not None:
        query = query.where(XpEvent.source_module.in_(sorted(modules)))
    with Session(engine) as s:
        rows = s.exec(query).all()
    for day, xp in rows:
        d = date.fromisoformat(day)
        out[d] = out.get(d, 0) + xp
    return out


def has_study_activity(signals: DaySignals, coach_xp: int) -> bool:
    return bool(coach_xp or any(getattr(signals, f) for f in STUDY_COUNT_FIELDS))


def is_active(signals: DaySignals, coach_xp: int, learning_only: bool) -> bool:
    """Ngày đáng gửi: learning → có học; general → có XP/wellbeing/focus (cùng tiêu chí trung bình tuần)."""
    return has_study_activity(signals, coach_xp) if learning_only else has_stat_activity(signals)


def collect_day(src: GrowthSources, day: date, learn: Optional[Set[str]] = None) -> DayAggregate:
    learn = learning_badge_ids() if learn is None else learn
    signals = collect_day_signals(src.engine, src.ledger, src.wellbeing, day)
    week = week_start_of(day)
    # chỉ số tích lũy tới hết ngày `day` (today=day → không lấy thêm ngày sau)
    stats = build_week_context(src.engine, src.ledger, src.wellbeing, week, day).stats_running[-1]
    # today = day+1 → decay của chính ngày `day` đã được áp (ngày đã kết thúc, báo cáo là bản đóng băng)
    progress = replay_week(src.ledger.daily_totals(week, day), week, day + timedelta(days=1))
    scope = getattr(src.ledger, "scope", None)
    unlocked = [(r.badge_id, local_date_of(r.unlocked_at)) for r in src.unlocks.list_all()]
    learn_rows = ([(b, d) for b, _, d in scoped_learning_unlocks(
        src.engine, src.ledger, src.wellbeing, src.unlocks, learn, day)] if scope else
        [(b, d) for b, d in unlocked if b in learn and d <= day])
    new_ids = sorted({b for b, d in unlocked if d == day})
    total_ids = {b for b, d in unlocked if d <= day}
    return DayAggregate(
        day=day, signals=signals, stats=stats, level=progress.level, pct=progress.pct,
        decayed=signals.xp_day < MIN_DAILY_XP, coach_xp=coach_xp_by_day(src.engine, day, day, scope and scope.modules).get(day, 0),
        badges_new=new_ids, badges_total=len(total_ids),
        learning_badges_new=sorted({b for b, d in learn_rows if d == day}),
        learning_badges_total=len({b for b, _ in learn_rows}))


def collect_week(src: GrowthSources, week: date, learn: Optional[Set[str]] = None) -> WeekAggregate:
    learn = learning_badge_ids() if learn is None else learn
    end = week + timedelta(days=6)
    ctx = build_week_context(src.engine, src.ledger, src.wellbeing, week, week + timedelta(days=7))
    totals = src.ledger.daily_totals(week, end)
    ids = sorted(src.unlocks.ids_for_week(week.isoformat()))
    ever = {r.badge_id for r in src.unlocks.list_all() if local_date_of(r.unlocked_at) <= end}
    scope = getattr(src.ledger, "scope", None)
    if scope:   # learning: huy hiệu học tập chỉ tính phần learner đích tự đạt
        mine = scoped_learning_unlocks(src.engine, src.ledger, src.wellbeing, src.unlocks, learn, end)
        learn_week, learn_total = [b for b, w, _ in mine if w == week.isoformat()], len({b for b, _, _ in mine})
    else:
        learn_week, learn_total = [b for b in ids if b in learn], len(ever & learn)
    return WeekAggregate(
        week_start=week, ctx=ctx, xp_earned=sum(v for v in totals.values() if v > 0),
        coach_xp=sum(coach_xp_by_day(src.engine, week, end, scope and scope.modules).values()),
        stats_end=running_stats(ctx), badges=ids, badges_total=len(ever), learning_badges=sorted(learn_week),
        learning_badges_total=learn_total)
