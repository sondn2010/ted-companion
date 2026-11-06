"""compute_due_reminders (thuần): T-15/T-5 đúng một lần, mở app muộn, cả ngày, nhiều họp cùng phút."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.engines.work.meeting_reminder_timing import compute_due_reminders, fired_key, minutes_until

START = datetime(2026, 10, 19, 3, 0, tzinfo=timezone.utc)  # 10:00 giờ UTC+7
OFFSETS = [15, 5]


def _ev(key="e1", start=START, all_day=False):
    return SimpleNamespace(key=key, start_at=start, all_day=all_day)


def _due(now, fired=None, events=None):
    return compute_due_reminders(events or [_ev()], now, OFFSETS, fired or set())


def test_t_minus_20_nothing():
    assert _due(START - timedelta(minutes=20)) == []


def test_t_minus_15_fires_15():
    (ev, offset, keys), = _due(START - timedelta(minutes=15))
    assert offset == 15 and keys == {fired_key("e1", 15)}


def test_t_minus_14_after_15_fired_nothing():
    assert _due(START - timedelta(minutes=14), fired={fired_key("e1", 15)}) == []


def test_t_minus_5_fires_5_and_marks_both():
    (_, offset, keys), = _due(START - timedelta(minutes=5), fired={fired_key("e1", 15)})
    assert offset == 5 and keys == {fired_key("e1", 15), fired_key("e1", 5)}


def test_app_started_at_t_minus_3_fires_only_5_and_marks_15():
    (_, offset, keys), = _due(START - timedelta(minutes=3))
    assert offset == 5 and fired_key("e1", 15) in keys  # không bắn T-15 muộn


def test_no_double_fire_after_restart_at_t_minus_3():
    assert _due(START - timedelta(minutes=2), fired={fired_key("e1", 15), fired_key("e1", 5)}) == []


def test_after_start_nothing():
    assert _due(START + timedelta(minutes=1)) == []
    assert _due(START) == []


def test_all_day_event_skipped():
    assert _due(START - timedelta(minutes=10), events=[_ev(all_day=True)]) == []


def test_two_events_same_minute_both_fire():
    due = _due(START - timedelta(minutes=15), events=[_ev("a"), _ev("b")])
    assert sorted(ev.key for ev, _o, _k in due) == ["a", "b"]


def test_naive_now_is_treated_as_local_without_typeerror():
    now_local_naive = (START - timedelta(minutes=15)).astimezone().replace(tzinfo=None)
    assert len(_due(now_local_naive)) == 1


def test_minutes_until_rounds_up_with_floor_of_one():
    assert minutes_until(START, START - timedelta(minutes=14, seconds=40)) == 15
    assert minutes_until(START, START - timedelta(seconds=10)) == 1
