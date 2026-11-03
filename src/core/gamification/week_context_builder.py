"""Dựng WeekContext (signals + stats + progress của 1 tuần) và gói thành WindowData cho evaluator / snapshot."""

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.engine import Engine
from sqlmodel import Session

from src.core.gamification.badge_metric_calculators import WindowData
from src.core.gamification.day_signals_collector import DaySignals, collect_day_signals
from src.core.gamification.gamification_table_models import WeeklySnapshot
from src.core.gamification.level_progression_engine import WeekProgress, replay_week
from src.core.gamification.weekly_running_stats import running_week_stats, stats_delta
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.wellbeing_stat_formulas import DayStats, compute_day_stats, has_stat_activity
from src.core.gamification.xp_ledger_repository import XpLedgerRepository


@dataclass
class WeekContext:
    week_start: date
    days: List[DaySignals]          # Thứ Hai → min(today, Chủ nhật)
    stats: List[DayStats]           # điểm THÔ từng ngày trong `days` (badge dùng)
    stats_running: List[DayStats]   # chỉ số tích lũy trong tuần cuối mỗi ngày (Hub/snapshot/báo cáo dùng)
    progress: WeekProgress
    prev_week_xp: int = 0
    prev_final_level: Optional[int] = None
    today: Optional[date] = None    # ngày "hiện tại" khi dựng ctx; ngày >= today chưa kết thúc

    def active_stats(self) -> List[DayStats]:
        return [st for sig, st in zip(self.days, self.stats) if has_stat_activity(sig)]

    def has_any_activity(self) -> bool:
        return any(has_stat_activity(s) for s in self.days)


def prev_week_info(engine: Engine, week_start: date) -> Tuple[int, Optional[int]]:
    """(xp_earned, final_level) của snapshot tuần trước; không có → (0, None)."""
    with Session(engine) as s:
        row = s.get(WeeklySnapshot, (week_start - timedelta(days=7)).isoformat())
    return (row.xp_earned, row.final_level) if row else (0, None)


def build_week_context(engine: Engine, ledger: XpLedgerRepository, wellbeing: WellbeingDailyRepository,
                       week_start: date, today: date, prev_week_xp: int = 0,
                       prev_final_level: Optional[int] = None) -> WeekContext:
    """today = ngày "hiện tại" (tuần đã kết thúc: truyền week_start+7 → mọi ngày tính là đã qua)."""
    last = min(today, week_start + timedelta(days=6))
    days = [collect_day_signals(engine, ledger, wellbeing, week_start + timedelta(days=i))
            for i in range((last - week_start).days + 1)]
    progress = replay_week(ledger.daily_totals(week_start, last), week_start, today)
    stats = [compute_day_stats(d) for d in days]
    running = running_week_stats(stats, [has_stat_activity(d) for d in days])
    return WeekContext(week_start, days, stats, running, progress, prev_week_xp, prev_final_level, today)


def running_stats(ctx: WeekContext) -> Dict[str, Optional[int]]:
    """6 chỉ số tích lũy tới ngày cuối của ctx (learning None nếu chưa từng có coach)."""
    return ctx.stats_running[-1].as_dict() if ctx.stats_running else {}


def running_stats_delta_today(ctx: WeekContext) -> Dict[str, Optional[int]]:
    """Thay đổi của từng chỉ số trong ngày cuối so với ngày trước (ngày đầu tuần: so với mốc 50)."""
    if not ctx.stats_running:
        return {}
    prev = ctx.stats_running[-2] if len(ctx.stats_running) > 1 else None
    return stats_delta(prev, ctx.stats_running[-1])


def stats_json(ctx: WeekContext) -> str:
    return json.dumps(running_stats(ctx))


def to_window_data_by_kind(ctx: WeekContext, lifetime_totals: Optional[Dict[str, float]] = None) -> Dict[str, object]:
    """{"day": [WindowData/ngày], "week": WindowData, "lifetime": WindowData (nếu có totals)} cho evaluate()."""
    common = dict(progress=ctx.progress, prev_week_xp=ctx.prev_week_xp, prev_final_level=ctx.prev_final_level)
    out: Dict[str, object] = {
        "day": [WindowData(days=[sig], stats=[st], **common) for sig, st in zip(ctx.days, ctx.stats)],
        "week": WindowData(days=ctx.days, stats=ctx.active_stats(), **common),
    }
    if ctx.today is not None:   # ngày đã kết thúc cho huy hiệu sức khỏe/năng lượng theo ngày
        out["day_final"] = [w for i, w in enumerate(out["day"]) if ctx.week_start + timedelta(days=i) < ctx.today]
    if lifetime_totals is not None:
        out["lifetime"] = WindowData(totals=lifetime_totals, **common)
    return out
