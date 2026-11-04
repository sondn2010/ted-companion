from datetime import time

import pytest

from src.engines.coach.coach_policy_clamp import DEFAULT_POLICY, apply_policy, clamp_policy, in_any_window
from src.engines.coach.coach_sync_plan_schemas import Policy

GOOD = {"review_interval_mins": 30, "daily_cap": 25, "new_per_day": 8, "leitner_days": [0.01, 1, 2, 4, 8, 16],
        "quiet_hours": ["21:45-06:30"], "study_windows": ["19:30-21:30"], "rationale": "ok"}


def test_default_policy_values():
    assert (DEFAULT_POLICY.review_interval_mins, DEFAULT_POLICY.daily_cap, DEFAULT_POLICY.new_per_day) == (15, 20, 10)
    assert DEFAULT_POLICY.leitner_days == [0.007, 1, 3, 7, 14, 30]


def test_valid_policy_is_accepted_unchanged():
    result = apply_policy(DEFAULT_POLICY, GOOD)
    assert result.review_interval_mins == 30 and result.leitner_days == GOOD["leitner_days"]
    assert result.quiet_hours == ["21:45-06:30"]


@pytest.mark.parametrize("field,raw,expected", [
    ("review_interval_mins", 5, 10), ("review_interval_mins", 500, 120),
    ("daily_cap", 99, 40), ("daily_cap", 1, 5), ("new_per_day", -3, 0), ("new_per_day", 50, 20),
])
def test_out_of_range_numbers_are_clamped(field, raw, expected):
    result = apply_policy(DEFAULT_POLICY, {**GOOD, field: raw})
    assert getattr(result, field) == expected


def test_leitner_days_values_clamped_to_bounds():
    result = apply_policy(DEFAULT_POLICY, {**GOOD, "leitner_days": [0.001, 1, 2, 3, 4, 1000]})
    assert result.leitner_days[0] == 0.003 and result.leitner_days[-1] == 365


def test_clamping_that_breaks_increasing_order_keeps_old():
    # 0.001 và 0.002 cùng bị kẹp thành 0.003 → không còn tăng dần
    assert apply_policy(DEFAULT_POLICY, {**GOOD, "leitner_days": [0.001, 0.002, 1, 2, 3, 4]}) is DEFAULT_POLICY


def test_five_leitner_days_keeps_old():
    assert apply_policy(DEFAULT_POLICY, {**GOOD, "leitner_days": [0.01, 1, 3, 7, 14]}) is DEFAULT_POLICY


def test_non_increasing_leitner_days_keeps_old():
    assert apply_policy(DEFAULT_POLICY, {**GOOD, "leitner_days": [0.01, 1, 1, 7, 14, 30]}) is DEFAULT_POLICY


def test_wrong_type_keeps_old():
    assert apply_policy(DEFAULT_POLICY, {**GOOD, "daily_cap": "nhiều"}) is DEFAULT_POLICY


def test_none_keeps_old():
    old = Policy.model_validate(GOOD)
    assert apply_policy(old, None) is old


def test_malformed_windows_are_dropped():
    raw = {**GOOD, "quiet_hours": ["21:45-06:30", "abc", "25:00-26:00", "9:00-10:00"], "study_windows": ["19:30-21:30", ""]}
    result = apply_policy(DEFAULT_POLICY, raw)
    assert result.quiet_hours == ["21:45-06:30"] and result.study_windows == ["19:30-21:30"]


def test_clamp_policy_does_not_mutate_input():
    policy = Policy.model_validate({**GOOD, "daily_cap": 99})
    assert clamp_policy(policy).daily_cap == 40 and policy.daily_cap == 99


def test_in_any_window_same_day_and_overnight():
    assert in_any_window(["19:30-21:30"], time(20, 0))
    assert not in_any_window(["19:30-21:30"], time(21, 30))   # cuối khung là loại trừ
    assert in_any_window(["21:45-06:30"], time(23, 0)) and in_any_window(["21:45-06:30"], time(5, 59))
    assert not in_any_window(["21:45-06:30"], time(12, 0))
    assert not in_any_window([], time(12, 0))
    assert not in_any_window(["bad"], time(12, 0))
