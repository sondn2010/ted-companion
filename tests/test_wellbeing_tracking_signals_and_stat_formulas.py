"""Phase 03 gamification: gap away theo ngày (07-22h), heartbeat, repo wellbeing, DaySignals, 6 chỉ số."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from src.core.app_state_key_value_store import KeyValueStore
from src.core.gamification.app_heartbeat_and_away_tracker import AppHeartbeatTracker, split_gap_waking_minutes
from src.core.gamification.day_signals_collector import (
    DaySignals, collect_day_signals, is_personal_event, longest_focus_chain)
from src.core.gamification.wellbeing_daily_repository import MAX_OUTINGS_PER_DAY, WellbeingDailyRepository
from src.core.gamification.wellbeing_stat_formulas import compute_day_stats, health_stat
from src.core.gamification.xp_ledger_repository import XpLedgerRepository
from src.core.models import FocusSession


@pytest.fixture
def repo(memory_engine):
    return WellbeingDailyRepository(memory_engine)


@pytest.fixture
def ledger(memory_engine):
    return XpLedgerRepository(memory_engine)


def test_gap_friday_18_to_sunday_20_counts_waking_hours_only():
    out = split_gap_waking_minutes(datetime(2026, 10, 23, 18, 0), datetime(2026, 10, 25, 20, 0))
    assert out == {date(2026, 10, 23): 4 * 60, date(2026, 10, 24): 15 * 60, date(2026, 10, 25): 13 * 60}


def test_gap_overnight_has_no_waking_minutes_and_negative_is_empty():
    assert split_gap_waking_minutes(datetime(2026, 10, 22, 23, 0), datetime(2026, 10, 23, 6, 0)) == {}
    assert split_gap_waking_minutes(datetime(2026, 10, 22, 12, 0), datetime(2026, 10, 22, 11, 0)) == {}


def test_first_run_no_gap_then_long_gap_adds_away(memory_engine, repo, ledger):
    tr = AppHeartbeatTracker(KeyValueStore(memory_engine), repo, ledger)
    t0 = datetime(2026, 10, 22, 9, 0)
    assert tr.on_app_start(t0) == {}
    assert tr.on_app_start(t0 + timedelta(minutes=5)) == {}              # < 10 phút: restart thường
    added = tr.on_app_start(t0 + timedelta(minutes=5 + 120))
    assert added == {date(2026, 10, 22): 120}
    assert repo.get(date(2026, 10, 22)).away_minutes == 120


def test_gap_over_30_days_ignored(memory_engine, repo, ledger):
    tr = AppHeartbeatTracker(KeyValueStore(memory_engine), repo, ledger)
    tr.on_app_start(datetime(2026, 8, 1, 9, 0))
    assert tr.on_app_start(datetime(2026, 10, 22, 9, 0)) == {}


def test_tick_counts_minutes_and_late_night(memory_engine, repo, ledger):
    tr = AppHeartbeatTracker(KeyValueStore(memory_engine), repo, ledger)
    tr.tick(datetime(2026, 10, 22, 14, 0))
    tr.tick(datetime(2026, 10, 22, 22, 30))   # tick đầu của lần chạy mới ở giờ khuya (heartbeat sau đó liên tục)
    row = repo.get(date(2026, 10, 22))
    # 14:00 → 22:30 là khoảng trống (máy ngủ): không tính Ted bật; chỉ 14:00 được tính, 22:30 là tick khôi phục
    assert (row.app_on_minutes, row.late_night_minutes) == (1, 0)
    tr.tick(datetime(2026, 10, 22, 22, 31))
    row = repo.get(date(2026, 10, 22))
    assert (row.app_on_minutes, row.late_night_minutes) == (2, 1)


def test_tick_after_pc_sleep_credits_away_not_app_on(memory_engine, repo, ledger):
    """Máy ngủ khi Ted còn mở: tick sau khi thức dậy cộng khoảng trống 07:00–22:00 vào away, không cộng app_on."""
    tr = AppHeartbeatTracker(KeyValueStore(memory_engine), repo, ledger)
    tr.tick(datetime(2026, 10, 22, 21, 0))
    assert tr.tick(datetime(2026, 10, 23, 8, 0)) is False
    assert repo.get(date(2026, 10, 22)).away_minutes == 60           # 21:00–22:00
    assert repo.get(date(2026, 10, 23)).away_minutes == 60           # 07:00–08:00
    assert repo.get(date(2026, 10, 23)).app_on_minutes == 0
    assert tr.tick(datetime(2026, 10, 23, 8, 1)) is True             # sau đó đếm bình thường
    assert repo.get(date(2026, 10, 23)).app_on_minutes == 1


def test_short_gap_tick_still_counts(memory_engine, repo, ledger):
    tr = AppHeartbeatTracker(KeyValueStore(memory_engine), repo, ledger)
    tr.tick(datetime(2026, 10, 22, 10, 0))
    assert tr.tick(datetime(2026, 10, 22, 10, 5)) is True            # < 10 phút: không phải ngủ máy
    assert repo.get(date(2026, 10, 22)).app_on_minutes == 2


def test_record_break_idempotent_per_minute(memory_engine, repo, ledger):
    tr = AppHeartbeatTracker(KeyValueStore(memory_engine), repo, ledger)
    now = datetime(2026, 10, 22, 10, 0)
    assert tr.record_break(now) and not tr.record_break(now)
    assert repo.get(date(2026, 10, 22)).breaks_taken == 1
    assert ledger.lifetime_counts()["break_taken"] == 1


def test_outing_cap_and_export(repo):
    d = date(2026, 10, 22)
    results = [repo.log_outing(d) for _ in range(MAX_OUTINGS_PER_DAY + 1)]
    assert results == [True] * MAX_OUTINGS_PER_DAY + [False]
    repo.add_away(d, 30)
    exported = repo.export_range(d, d)
    assert exported[0]["outings"] == MAX_OUTINGS_PER_DAY and exported[0]["away_minutes"] == 30
    assert set(exported[0]) == {"local_date", "app_on_minutes", "away_minutes", "breaks_taken", "outings",
                                "late_night_minutes", "micro_breaks_done", "micro_water_done", "micro_move_done"}
    assert (exported[0]["micro_breaks_done"], exported[0]["micro_water_done"], exported[0]["micro_move_done"]) == (0, 0, 0)
    repo.log_micro_break(d, "water")
    assert repo.export_range(d, d)[0]["micro_breaks_done"] == 1 and repo.export_range(d, d)[0]["micro_water_done"] == 1


def test_focus_chain_resets_on_gap_or_break():
    t = datetime(2026, 10, 22, 8, 0)
    s = [(t, t + timedelta(minutes=50), 50), (t + timedelta(minutes=52), t + timedelta(minutes=102), 50)]
    assert longest_focus_chain(s, []) == 100
    assert longest_focus_chain(s, [t + timedelta(minutes=51)]) == 50
    far = [s[0], (t + timedelta(minutes=70), t + timedelta(minutes=100), 30)]
    assert longest_focus_chain(far, []) == 50


def test_personal_event_heuristic():
    mon = datetime(2026, 10, 19, 9, 0)
    assert not is_personal_event(mon, mon + timedelta(hours=1), False)
    assert is_personal_event(mon, mon + timedelta(hours=24), True)
    assert is_personal_event(mon.replace(hour=19), mon.replace(hour=20), False)
    assert is_personal_event(mon.replace(hour=6), mon.replace(hour=8), False)
    sat = datetime(2026, 10, 24, 10, 0)
    assert is_personal_event(sat, sat + timedelta(hours=1), False)


def test_collect_day_signals_from_db(memory_engine, repo, ledger):
    day = date(2026, 10, 22)
    start = datetime(2026, 10, 22, 9, 0).astimezone(timezone.utc)
    with Session(memory_engine) as s:
        s.add(FocusSession(actual_minutes=50, distraction_count=0, started_at=start,
                           ended_at=start + timedelta(minutes=50)))
        s.add(FocusSession(actual_minutes=40, distraction_count=2, started_at=start + timedelta(minutes=52),
                           ended_at=start + timedelta(minutes=92)))
        s.commit()
    ts = datetime(2026, 10, 22, 5, 0, tzinfo=timezone.utc)
    ledger.add("t1", ts, "work", "work", "task_done", {"category": "x"})
    for i in range(3):
        ledger.add(f"q{i}", ts, "thcs", "coach", "quiz_answered")
    ledger.add("c0", ts, "thcs", "coach", "quiz_correct")
    repo.add_minutes(day, 120)
    sig = collect_day_signals(memory_engine, ledger, repo, day)
    assert (sig.focus_minutes, sig.sessions, sig.clean_sessions, sig.focus_chain_max) == (90, 2, 1, 90)
    assert (sig.tasks_done, sig.quiz_answered, sig.quiz_correct, sig.quiz_wrong) == (1, 3, 1, 2)
    assert sig.app_on_minutes == 120 and sig.has_coach and sig.accuracy_7d == 0.5 and sig.study_days_7d == 1


def test_stats_all_zero_boundaries():
    st = compute_day_stats(DaySignals())
    assert (st.data, st.screen_load, st.engagement, st.energy) == (0, 0, 0, round(0.3 * 50 + 20))
    assert st.health == 50 and st.learning is None


def test_stats_clamped_at_100():
    st = compute_day_stats(DaySignals(
        quiz_correct=100, focus_minutes=999, app_on_minutes=9999, focus_chain_max=999, personal_event_minutes=9999,
        outings=3, away_minutes=999, work_meeting_minutes=999, xp_day=999, xp_7d_avg=999, has_coach=True,
        study_days_7d=7, accuracy_7d=1.0))
    assert (st.data, st.screen_load, st.engagement, st.learning) == (100, 100, 100, 100)
    assert 0 <= st.health <= 100 and 0 <= st.energy <= 100


def test_travel_day_health_at_least_85_and_engagement_up():
    st = compute_day_stats(DaySignals(away_minutes=15 * 60))
    assert st.health >= 85 and st.engagement >= 20


def test_overworked_day_health_drops_below_baseline():
    over = DaySignals(app_on_minutes=600, break_minutes=10, breaks=2, focus_chain_max=150, late_night_minutes=60)
    rested = health_stat(DaySignals(app_on_minutes=300, away_minutes=120, break_minutes=25, breaks=5))
    assert rested > 50 > health_stat(over)
    assert compute_day_stats(over).health < 30
