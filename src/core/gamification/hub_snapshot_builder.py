"""Dựng HubSnapshot từ DB (không Qt)."""

import json
from datetime import date
from typing import List

from sqlalchemy.engine import Engine

from src.core.gamification.badge_unlock_repository import BadgeUnlockRepository
from src.core.gamification.hub_snapshot_model import HubSnapshot, WeeklyLogRow
from src.core.gamification.level_progression_engine import week_start_of
from src.core.gamification.week_context_builder import (
    build_week_context, prev_week_info, running_stats, running_stats_delta_today)
from src.core.gamification.weekly_snapshot_service import WeeklySnapshotService
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.xp_ledger_repository import XpLedgerRepository

WEEKLY_LOG_ROWS = 12


def build_hub_snapshot(engine: Engine, ledger: XpLedgerRepository, wellbeing: WellbeingDailyRepository,
                       unlocks: BadgeUnlockRepository, snapshots: WeeklySnapshotService, today: date) -> HubSnapshot:
    week = week_start_of(today)
    prev_xp, prev_level = prev_week_info(engine, week)
    ctx = build_week_context(engine, ledger, wellbeing, week, today, prev_xp, prev_level)
    totals = ledger.daily_totals(week, today)
    log: List[WeeklyLogRow] = []
    for row in snapshots.list_recent(WEEKLY_LOG_ROWS):
        try:
            stats = json.loads(row.stats_json)
        except ValueError:
            stats = {}
        log.append(WeeklyLogRow(row.week_start, row.final_level, row.peak_level, row.final_pct, row.xp_earned, row.active_days,
                                row.decay_days, stats, snapshots.badges_of(row)))
    ever = unlocks.ever_unlocked_ids()
    p = ctx.progress
    return HubSnapshot(
        today=today, week_start=week, level=p.level, peak_level=p.peak_level, pct=p.pct,
        pct_today_delta=p.pct_today_delta, xp_today=totals.get(today, 0),
        week_xp=sum(v for v in totals.values() if v > 0), active_days=p.active_days, decay_days=p.decay_days,
        stats=running_stats(ctx), stats_delta_today=running_stats_delta_today(ctx),
        badges_unlocked=frozenset(ever), badges_this_week=frozenset(unlocks.ids_for_week(week.isoformat())),
        distinct_badge_count=len(ever), weekly_log=log)
