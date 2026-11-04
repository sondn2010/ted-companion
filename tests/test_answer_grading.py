import json

import pytest

from src.engines.coach.answer_grading import grade_answer, grade_step, normalize_text
from src.engines.coach.coach_data_models import QuizItem


def _mcq():
    return QuizItem(module_id="m", type="mcq", question="She ___ in Hanoi", answer="B", content_hash="h",
                    choices_json=json.dumps(["A. lives", "B. has lived", "C. lived", "D. is living"]))


def _short(answer):
    return QuizItem(module_id="m", type="short", question="q", answer=answer, content_hash="h")


@pytest.mark.parametrize("reply", ["B", "b", " b ", "B. has lived", "b) has lived", "has lived", "HAS  Lived"])
def test_mcq_correct_variants(reply):
    assert grade_answer(_mcq(), reply) is True


@pytest.mark.parametrize("reply", ["A", "c", "A. lives", "lived", "", "a lot"])
def test_mcq_wrong_variants(reply):
    assert grade_answer(_mcq(), reply) is False


def test_short_ignores_case_diacritics_and_spacing():
    item = _short("Hà  Nội")
    assert grade_answer(item, "ha noi") and grade_answer(item, "  HÀ NỘI ")
    assert grade_answer(_short("Đà Nẵng"), "da nang")


def test_short_wrong_and_cjk():
    assert not grade_answer(_short("准备 (zhǔnbèi)"), "准备")
    assert grade_answer(_short("准备 (zhǔnbèi)"), "准备 (zhunbei)")
    assert not grade_answer(_short("cat"), "dog")


def test_step_self_assessment():
    item = QuizItem(module_id="m", type="step", question="q", answer="sol", content_hash="h")
    assert grade_answer(item, "Làm được") is True
    assert grade_answer(item, "Chưa được") is False
    assert grade_step("chua duoc") is False
    with pytest.raises(ValueError):
        grade_step("có thể")


def test_normalize_text():
    assert normalize_text("  Ế  Đ ") == "e d"
