"""Cổng nhắc ôn: PAUSED/DEEP_WORK chặn mọi trường hợp, giờ yên lặng qua nửa đêm, cap, snooze, khung học..."""

from datetime import date, datetime, timedelta, timezone

import pytest

from src.core.focus_engine import FocusState
from src.engines.coach.coach_policy_clamp import DEFAULT_POLICY
from src.engines.coach.coach_prompt_round_robin_arbiter import RoundRobinArbiter
from src.engines.coach.coach_review_prompt_gate import should_prompt

TZ = timezone(timedelta(hours=7))
QUIET = DEFAULT_POLICY.model_copy(update={"quiet_hours": ["22:00-07:00"]})
WINDOWED = DEFAULT_POLICY.model_copy(update={"study_windows": ["19:00-21:00"]})


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 19, hour, minute, tzinfo=TZ)


def gate(now=None, state=FocusState.IDLE, policy=DEFAULT_POLICY, **kw):
    args = dict(attempts_today=0, due_count=3, new_available=0)
    args.update(kw)
    return should_prompt(now or at(12), state, policy, **args)


def test_idle_with_due_prompts():
    assert gate() == (True, "ok")


@pytest.mark.parametrize("state", [FocusState.DEEP_WORK_RUNNING, FocusState.PAUSED])
def test_focus_states_block_even_when_everything_else_allows(state):
    assert gate(state=state, due_count=50, new_available=50) == (False, "focus_session")


def test_break_prompts():
    assert gate(state=FocusState.BREAK_RUNNING)[0] is True


@pytest.mark.parametrize(
    "hour,minute,expected", [(23, 30, False), (6, 59, False), (7, 0, True), (21, 59, True), (22, 0, False)])
def test_quiet_hours_wrap_midnight(hour, minute, expected):
    assert gate(at(hour, minute), policy=QUIET)[0] is expected


def test_break_inside_quiet_hours_is_blocked():
    assert gate(at(23), state=FocusState.BREAK_RUNNING, policy=QUIET) == (False, "quiet_hours")


def test_daily_cap_reached():
    assert gate(attempts_today=DEFAULT_POLICY.daily_cap) == (False, "daily_cap")
    assert gate(attempts_today=DEFAULT_POLICY.daily_cap - 1)[0] is True


def test_snooze_until():
    assert gate(snooze_until=at(12, 10)) == (False, "snoozed")
    assert gate(at(12, 10), snooze_until=at(12, 10))[0] is True


def test_skip_today_only_blocks_that_date():
    assert gate(skip_date=date(2026, 10, 19)) == (False, "skipped_today")
    assert gate(skip_date=date(2026, 10, 18))[0] is True


def test_meeting_blocks():
    assert gate(in_meeting=True) == (False, "in_meeting")


def test_nothing_due_nor_new():
    assert gate(due_count=0, new_available=0) == (False, "nothing_to_review")


def test_outside_window_with_only_new_items_is_false():
    assert gate(policy=WINDOWED, due_count=0, new_available=5) == (False, "outside_study_window")


def test_outside_window_with_due_items_is_true():
    assert gate(policy=WINDOWED, due_count=2)[0] is True


def test_inside_window_with_only_new_items_is_true():
    assert gate(at(19, 30), policy=WINDOWED, due_count=0, new_available=5)[0] is True


def test_break_outside_window_with_only_new_items_checks_at_once():
    assert gate(state=FocusState.BREAK_RUNNING, policy=WINDOWED, due_count=0, new_available=5)[0] is True


# ---- round-robin (Red Team #11) ----
def test_arbiter_gives_turn_to_longest_waiting_module():
    arb, now = RoundRobinArbiter(), at(12)
    arb.record_prompt("thcs", now)             # thcs vừa được nhắc
    arb.mark_waiting("duhoc", now)             # duhoc bị chặn vì bong bóng bận
    assert arb.may_prompt("thcs", now + timedelta(minutes=15)) is False
    assert arb.may_prompt("duhoc", now + timedelta(minutes=15)) is True
    arb.record_prompt("duhoc", now + timedelta(minutes=15))
    assert arb.may_prompt("thcs", now + timedelta(minutes=16)) is True


def test_arbiter_waiting_never_expires_by_time_but_forget_clears():
    arb, now = RoundRobinArbiter(), at(12)
    arb.record_prompt("thcs", now)
    arb.mark_waiting("duhoc", now)
    assert arb.may_prompt("thcs", now + timedelta(hours=5)) is False        # interval dài vẫn nhường duhoc (H1)
    arb.forget("duhoc")                                                      # duhoc tắt / hết đủ điều kiện
    assert arb.may_prompt("thcs", now + timedelta(hours=5)) is True


def test_arbiter_simulation_two_coaches_no_starvation_for_long_intervals():
    for interval in (15, 30, 120):
        arb, t, shown = RoundRobinArbiter(), at(8), {"A": 0, "B": 0}
        for _ in range(16):
            busy_until = None
            for m in ("B", "A"):                  # B luôn tick trước A (cùng interval, B start trước)
                now = t + timedelta(seconds=1 if m == "A" else 0)
                if (busy_until is not None and now < busy_until) or not arb.may_prompt(m, now):
                    arb.mark_waiting(m, now)
                    continue
                arb.record_prompt(m, now)
                shown[m] += 1
                busy_until = now + timedelta(seconds=45)
            t += timedelta(minutes=interval)
        assert abs(shown["A"] - shown["B"]) <= 1 and shown["A"] >= 7, (interval, shown)
