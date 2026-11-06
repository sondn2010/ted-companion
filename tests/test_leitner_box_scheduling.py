from datetime import datetime, timedelta, timezone

import pytest

from src.engines.coach.leitner_box_scheduling import next_review

NOW = datetime(2026, 10, 19, 5, 0, tzinfo=timezone.utc)
DEFAULT = [0.007, 1, 3, 7, 14, 30]


@pytest.mark.parametrize("box", range(5))
def test_correct_moves_up_one_box_with_default_days(box):
    out = next_review(box, 0, True, NOW, DEFAULT)
    assert out.box == box + 1 and out.lapses == 0
    assert out.due_at == NOW + timedelta(days=DEFAULT[box + 1])


def test_correct_caps_at_box_5():
    out = next_review(5, 0, True, NOW, DEFAULT)
    assert out.box == 5 and out.due_at == NOW + timedelta(days=30)


@pytest.mark.parametrize("box", range(6))
def test_wrong_goes_to_box_0_and_counts_lapse(box):
    out = next_review(box, 2, False, NOW, DEFAULT)
    assert out.box == 0 and out.lapses == 3
    assert out.due_at == NOW + timedelta(days=0.007)


def test_custom_days_from_policy_are_used():
    custom = [0.01, 2, 4, 8, 16, 32]
    assert next_review(0, 0, True, NOW, custom).due_at == NOW + timedelta(days=2)
    assert next_review(4, 0, True, NOW, custom).due_at == NOW + timedelta(days=32)


def test_naive_now_is_rejected():
    with pytest.raises(ValueError):
        next_review(0, 0, True, datetime(2026, 10, 19, 5, 0), DEFAULT)


def test_requires_six_days():
    with pytest.raises(ValueError):
        next_review(0, 0, True, NOW, [1, 2, 3])
