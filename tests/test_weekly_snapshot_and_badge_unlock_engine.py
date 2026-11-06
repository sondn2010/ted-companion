"""Phase 04 gamification: metric registry, evaluator (day/week/lifetime), unlock repo, snapshot backfill."""

import json
from datetime import date, datetime, timezone

import pytest

from src.core.gamification.badge_catalog_loader import load_badge_catalog
from src.core.gamification.badge_metric_calculators import METRICS, WindowData, longest_streak
from src.core.gamification.badge_unlock_evaluator import evaluate
from src.core.gamification.badge_unlock_repository import BadgeUnlockRepository
from src.core.gamification.badge_unlock_service import BadgeUnlockService
from src.core.gamification.day_signals_collector import DaySignals
from src.core.gamification.level_progression_engine import WeekProgress
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.wellbeing_stat_formulas import compute_day_stats
from src.core.gamification.weekly_snapshot_service import WeeklySnapshotService
from src.core.gamification.xp_ledger_repository import XpLedgerRepository

CATALOG = load_badge_catalog(strict=True)


def _week(days, **kw) -> WindowData:
    return WindowData(days=days, stats=[compute_day_stats(d) for d in days], **kw)


def _ids(windows, week=frozenset(), ever=frozenset()):
    return set(evaluate(CATALOG, windows, set(week), set(ever)))


def test_every_catalog_rule_and_guard_uses_registered_metric():
    for b in CATALOG.badges:
        assert b.rule.metric in METRICS, b.id
        if b.rule.min:
            assert b.rule.min.metric in METRICS, b.id


def test_longest_streak():
    d = lambda n: date(2026, 10, n)  # noqa: E731
    assert longest_streak({d(1): 30, d(2): 20, d(3): 5, d(4): 50, d(5): 50, d(6): 99}) == 3
    assert longest_streak({}) == 0


def test_day_window_unlocks_only_matching_focus_tiers():
    days = [DaySignals(focus_minutes=120, xp_day=60), DaySignals(focus_minutes=10)]
    windows = {"day": [_week([d]) for d in days], "week": _week(days)}
    got = _ids(windows)
    assert {"focus_day_bronze", "focus_day_silver"} <= got
    assert "focus_day_gold" not in got and "focus_week_silver" not in got


def test_already_unlocked_this_week_is_skipped_but_lifetime_uses_ever():
    days = [DaySignals(focus_minutes=60, sessions=1)]
    windows = {"day": [_week(days)], "week": _week(days),
               "lifetime": WindowData(totals={"focus_sessions": 3, "focus_minutes": 10})}
    assert "focus_day_bronze" not in _ids(windows, week={"focus_day_bronze"})
    assert "focus_first_session" in _ids(windows)
    assert "focus_first_session" not in _ids(windows, ever={"focus_first_session"})
    assert "focus_first_session" not in _ids({k: v for k, v in windows.items() if k != "lifetime"})


def test_accuracy_requires_min_answers():
    few = _week([DaySignals(quiz_answered=10, quiz_correct=10)])
    many = _week([DaySignals(quiz_answered=20, quiz_correct=20)])
    assert "quiz_accuracy_week_gold" not in _ids({"day": [], "week": few})
    assert "quiz_accuracy_week_gold" in _ids({"day": [], "week": many})


def test_screen_balance_needs_three_active_days():
    quiet = DaySignals(xp_day=30, app_on_minutes=60)
    assert "screen_balance_week" not in _ids({"day": [], "week": _week([quiet, quiet])})
    assert "screen_balance_week" in _ids({"day": [], "week": _week([quiet] * 3)})


def test_week_growth_and_level_growth_use_previous_snapshot():
    days = [DaySignals(xp_day=150)]
    prog = WeekProgress(level=4, peak_level=4)
    up = _week(days, progress=prog, prev_week_xp=100, prev_final_level=2)
    flat = _week(days, progress=prog, prev_week_xp=1000, prev_final_level=4)
    assert {"week_growth", "level_growth"} <= _ids({"day": [], "week": up})
    got = _ids({"day": [], "week": flat})
    assert "week_growth" not in got and "level_growth" not in got


def test_perfect_week_and_peak_level():
    days = [DaySignals(xp_day=30)] * 7
    got = _ids({"day": [], "week": _week(days, progress=WeekProgress(peak_level=7, level=7))})
    assert {"perfect_week", "level_five"} <= got and "level_max" not in got
    # huy hiệu là cột mốc giữ vĩnh viễn: chạm Lv5 (kể cả mốc 50% đầu tuần) là mở, không có ngưỡng cao hơn
    assert "level_five" in _ids({"day": [], "week": _week(days, progress=WeekProgress(peak_level=5, level=5))})
    assert "level_five" not in _ids({"day": [], "week": _week(days, progress=WeekProgress(peak_level=4, level=4))})


def test_unlock_repository_idempotent_and_distinct_count(memory_engine):
    repo = BadgeUnlockRepository(memory_engine)
    assert repo.add("a", "2026-10-12") and not repo.add("a", "2026-10-12")
    assert repo.add("a", "2026-10-19") and repo.add("b", "2026-10-19")
    assert repo.distinct_unlocked_count() == 2
    assert repo.ids_for_week("2026-10-19") == {"a", "b"}


@pytest.fixture
def services(memory_engine):
    ledger = XpLedgerRepository(memory_engine)
    wb = WellbeingDailyRepository(memory_engine)
    unlocks = BadgeUnlockRepository(memory_engine)
    return ledger, wb, unlocks, WeeklySnapshotService(memory_engine, ledger, wb, unlocks, catalog=CATALOG)


def _add_tasks(ledger, day, n):
    ts = datetime(2026, 10, day, 5, 0, tzinfo=timezone.utc)
    for i in range(n):
        ledger.add(f"task_done:{day}-{i}:1", ts, "work", "work", "task_done", {"category": "x"})


def test_backfill_creates_snapshot_is_idempotent_and_unlocks_badges(memory_engine, services):
    ledger, wb, unlocks, svc = services
    _add_tasks(ledger, 13, 5)                       # tuần 2026-10-12: 5 task = 75 XP
    today = date(2026, 10, 22)                      # tuần hiện tại 2026-10-19 → không lưu
    assert svc.backfill(today) == 1
    assert svc.backfill(today) == 0
    rows = svc.list_recent()
    assert [r.week_start for r in rows] == ["2026-10-12"]
    row = rows[0]
    assert row.xp_earned == 75 and row.active_days == 1 and row.decay_days >= 1
    assert "tasks_week_bronze" in svc.badges_of(row)
    assert "tasks_week_bronze" in unlocks.ids_for_week("2026-10-12")
    assert set(json.loads(row.stats_json)) == {"data", "learning", "screen_load", "health", "engagement", "energy"}


def test_backfill_empty_ledger_and_empty_weeks(services):
    ledger, _, _, svc = services
    assert svc.backfill(date(2026, 10, 22)) == 0
    _add_tasks(ledger, 6, 2)                        # tuần 2026-10-05; tuần 10-12 trống
    assert svc.backfill(date(2026, 10, 22)) == 1
    assert [r.week_start for r in svc.list_recent()] == ["2026-10-05"]


def test_refresh_if_week_changed_uses_kv(memory_engine, services):
    from src.core.app_state_key_value_store import KeyValueStore
    ledger, wb, unlocks, _ = services
    svc = WeeklySnapshotService(memory_engine, ledger, wb, unlocks, KeyValueStore(memory_engine), CATALOG)
    _add_tasks(ledger, 13, 5)
    assert svc.refresh_if_week_changed(date(2026, 10, 22)) == 1
    _add_tasks(ledger, 6, 5)                        # dữ liệu muộn cho tuần cũ
    assert svc.refresh_if_week_changed(date(2026, 10, 23)) == 0   # cùng tuần → bỏ qua
    assert svc.refresh_if_week_changed(date(2026, 10, 26)) == 1   # sang tuần mới → backfill tuần 10-05


def test_live_unlock_service_current_week_and_lifetime(memory_engine, services):
    ledger, wb, unlocks, _ = services
    _add_tasks(ledger, 20, 5)
    svc = BadgeUnlockService(memory_engine, ledger, wb, unlocks, CATALOG)
    first = {b.id for b in svc.refresh(date(2026, 10, 22))}
    assert "tasks_week_bronze" in first and "tasks_lifetime_100" not in first
    assert svc.refresh(date(2026, 10, 22)) == []
    assert unlocks.distinct_unlocked_count() == len(first)
