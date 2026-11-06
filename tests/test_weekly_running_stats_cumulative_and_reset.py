"""Phase 12: 6 chỉ số tích lũy trong tuần, thứ Hai bắt đầu 50, delta = (điểm ngày − 50)·scale, kẹp 0..100."""

from datetime import date, datetime, timedelta, timezone

from src.core.gamification.week_context_builder import build_week_context, running_stats, running_stats_delta_today
from src.core.gamification.weekly_running_stats import STAT_DELTA_SCALE, running_week_stats, stat_delta, stats_delta
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.wellbeing_stat_formulas import DayStats
from src.core.gamification.xp_ledger_repository import XpLedgerRepository

MON = date(2026, 10, 19)


def _day(score, learning=None) -> DayStats:
    return DayStats(data=score, learning=learning, screen_load=score, health=score, engagement=score, energy=score)


def test_delta_formula_and_none_learning():
    assert stat_delta(100) == 50 * STAT_DELTA_SCALE and stat_delta(0) == -50 * STAT_DELTA_SCALE
    assert stat_delta(50) == 0 and stat_delta(None) == 0


def test_monday_without_activity_starts_all_stats_at_fifty():
    out = running_week_stats([_day(0)], [False])
    assert out[0] == DayStats(data=50, learning=None, screen_load=50, health=50, engagement=50, energy=50)


def test_stats_carry_over_day_to_day_within_week():
    out = running_week_stats([_day(100), _day(100), _day(50)], [True, True, True])
    assert [d.data for d in out] == [70, 90, 90]   # +20, +20, 0
    out = running_week_stats([_day(0), _day(100)], [True, True])
    assert [d.health for d in out] == [30, 50]     # xấu rồi tốt: cộng dồn, không reset


def test_inactive_day_does_not_change_running_values():
    out = running_week_stats([_day(100), _day(0), _day(100)], [True, False, True])
    assert [d.energy for d in out] == [70, 70, 90]


def test_running_values_clamped_to_0_and_100():
    up = running_week_stats([_day(100)] * 5, [True] * 5)
    assert up[-1].data == 100
    down = running_week_stats([_day(0)] * 5, [True] * 5)
    assert down[-1].data == 0


def test_learning_none_until_coach_then_starts_at_fifty():
    out = running_week_stats([_day(80), _day(80, learning=100), _day(80)], [True, True, True])
    assert out[0].learning is None
    assert out[1].learning == 70 and out[2].learning == 70   # 50 + 0.4·50; ngày sau không có điểm → giữ nguyên


def test_stats_delta_vs_previous_day():
    a, b = _day(100), _day(100)
    out = running_week_stats([a, b], [True, True])
    assert stats_delta(out[0], out[1])["data"] == 20 and stats_delta(None, out[0])["data"] == 20


def _seed(engine, day: date, xp_tasks: int):
    ledger = XpLedgerRepository(engine)
    ts = datetime(day.year, day.month, day.day, 5, 0, tzinfo=timezone.utc)
    for i in range(xp_tasks):
        ledger.add(f"task_done:{day}-{i}:1", ts, "work", "work", "task_done", {"category": "x"})
    return ledger


def test_week_context_accumulates_then_resets_next_monday(memory_engine):
    wb = WellbeingDailyRepository(memory_engine)
    ledger = _seed(memory_engine, MON, 20)             # thứ Hai làm việc
    wed = MON + timedelta(days=2)
    ledger = _seed(memory_engine, wed, 20)             # thứ Tư làm việc
    ctx = build_week_context(memory_engine, ledger, wb, MON, wed)
    assert len(ctx.stats_running) == 3
    data = [s.data for s in ctx.stats_running]
    assert data == [70, 70, 90]   # 20 task = điểm ngày 100 → +20; thứ Ba trống → giữ nguyên
    assert running_stats(ctx)["data"] == data[2]
    assert running_stats_delta_today(ctx)["data"] == data[2] - data[1]
    next_mon = MON + timedelta(days=7)
    fresh = build_week_context(memory_engine, ledger, wb, next_mon, next_mon)
    assert running_stats(fresh) == {"data": 50, "learning": None, "screen_load": 50, "health": 50,
                                    "engagement": 50, "energy": 50}
    assert fresh.progress.pct == 50


def test_legacy_weekly_snapshot_table_gains_final_pct_column(memory_engine):
    from sqlalchemy import inspect, text
    from src.core.gamification.gamification_columns_migration import ensure_gamification_columns
    with memory_engine.begin() as c:   # bảng cũ (trước phase 12): không có final_pct
        c.execute(text("DROP TABLE weeklysnapshot"))
        c.execute(text("CREATE TABLE weeklysnapshot (week_start VARCHAR PRIMARY KEY, final_level INTEGER, "
                       "peak_level INTEGER, xp_earned INTEGER, final_balance INTEGER, active_days INTEGER, "
                       "decay_days INTEGER, stats_json VARCHAR, badges_json VARCHAR, created_at DATETIME)"))
        c.execute(text("INSERT INTO weeklysnapshot VALUES ('2026-10-12', 6, 7, 500, 820, 5, 1, '{}', '[]', '2026-10-19')"))
    ensure_gamification_columns(memory_engine)
    assert "final_pct" in {col["name"] for col in inspect(memory_engine).get_columns("weeklysnapshot")}
    with memory_engine.connect() as c:
        assert c.execute(text("SELECT final_pct FROM weeklysnapshot")).scalar() == 50.0
