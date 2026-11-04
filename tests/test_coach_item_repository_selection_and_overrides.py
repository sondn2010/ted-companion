from datetime import timedelta

import pytest

from src.engines.coach.coach_local_day import day_bounds_utc
from src.engines.coach.coach_data_models import ReviewState, content_hash, open_session
from src.engines.coach.coach_sync_plan_schemas import SrsOverride
from coach_test_support import DAYS, MODULE, NOW, TZ, quiz, repos, seed


def _day_start():
    return day_bounds_utc(NOW.astimezone(TZ).date(), TZ)[0]


def _answer(attempts, item, correct, when=NOW, secs=10):
    return attempts.record_answer(MODULE, item.id, "ans", correct, secs, when, DAYS)


def test_dedupe_insert_skips_existing_and_in_batch_duplicates(memory_engine):
    items, _ = repos(memory_engine)
    batch = [quiz("Q1"), quiz("  q1 "), quiz("Q2")]   # "  q1 " trùng Q1 sau chuẩn hoá
    assert items.insert_items_dedup(MODULE, batch, NOW) == 2
    assert items.insert_items_dedup(MODULE, [quiz("Q1"), quiz("Q3")], NOW) == 1
    # cùng câu ở module khác vẫn được chèn
    assert items.insert_items_dedup("duhoc", [quiz("Q1")], NOW) == 1


def test_content_hash_depends_on_topic_and_normalized_question():
    assert content_hash("a.b", "Hello  World") == content_hash("a.b", "hello world")
    assert content_hash("a.b", "x") != content_hash("a.c", "x")


def test_naive_datetime_is_rejected_everywhere(memory_engine):
    items, _ = repos(memory_engine)
    with pytest.raises(ValueError):
        items.insert_items_dedup(MODULE, [quiz("Q1")], NOW.replace(tzinfo=None))


def test_new_items_limited_by_new_per_day(memory_engine):
    items, attempts = repos(memory_engine)
    qs = seed(memory_engine, [f"Q{i}" for i in range(6)])
    assert len(items.select_for_review(MODULE, NOW, 10, 3, _day_start())) == 3
    _answer(attempts, qs[0], True)   # 1 câu mới đã hỏi hôm nay → còn room 2 (câu kia chưa đến hạn)
    picked = items.select_for_review(MODULE, NOW, 10, 3, _day_start())
    assert len(picked) == 2 and qs[0].id not in {p.id for p in picked}
    assert items.select_for_review(MODULE, NOW, 10, 0, _day_start()) == []


def test_due_items_ordered_by_box_then_due_then_new_after(memory_engine):
    items, attempts = repos(memory_engine)
    a, b, c, d = seed(memory_engine, ["A", "B", "C", "D"])
    past = NOW - timedelta(days=40)
    _answer(attempts, a, True, past)            # box 1
    _answer(attempts, a, True, past + timedelta(days=2))   # box 2
    _answer(attempts, b, True, past)            # box 1
    _answer(attempts, c, False, past)           # box 0
    picked = items.select_for_review(MODULE, NOW, 10, 10, _day_start() + timedelta(days=5))
    assert [p.question for p in picked] == ["C", "B", "A", "D"]   # box 0, 1, 2, rồi câu mới
    assert items.due_count(MODULE, NOW) == 3


def test_not_due_items_excluded_and_limit_applies(memory_engine):
    items, attempts = repos(memory_engine)
    a, b = seed(memory_engine, ["A", "B"])
    _answer(attempts, a, True, NOW)   # due sau 1 ngày
    picked = items.select_for_review(MODULE, NOW, 10, 0, _day_start())
    assert picked == []
    assert len(items.select_for_review(MODULE, NOW + timedelta(days=2), 1, 10, _day_start())) == 1


def test_flagged_and_retired_never_selected_or_counted(memory_engine):
    items, attempts = repos(memory_engine)
    a, b, c = seed(memory_engine, ["A", "B", "C"])
    items.flag_item(a.id, "đáp án sai")
    items.apply_overrides(MODULE, [SrsOverride(item_id=b.id, action="retire")], NOW)
    assert [p.question for p in items.select_for_review(MODULE, NOW, 10, 10, _day_start())] == ["C"]
    assert items.unseen_count(MODULE) == 1
    assert items.get(a.id).flag_reason == "đáp án sai"


def test_flag_unknown_item_returns_false(memory_engine):
    items, _ = repos(memory_engine)
    assert items.flag_item("nope", "x") is False


def test_topic_filter_for_selection_and_unseen_count(memory_engine):
    items, _ = repos(memory_engine)
    seed(memory_engine, ["E1", "E2"], topic="english.conditionals")
    seed(memory_engine, ["M1"], topic="math.inequalities")
    assert items.unseen_count(MODULE) == 3
    assert items.unseen_count(MODULE, "math.inequalities") == 1
    assert [p.question for p in items.select_for_review(MODULE, NOW, 10, 10, _day_start(), "math.inequalities")] == ["M1"]


def test_unseen_count_filters_by_types(memory_engine):
    items, _ = repos(memory_engine)
    items.insert_items_dedup(MODULE, [quiz("S1", type_="step", answer="sol"), quiz("Q1")], NOW)
    assert items.unseen_count(MODULE, types=["step"]) == 1


def test_modules_are_isolated(memory_engine):
    items, _ = repos(memory_engine)
    seed(memory_engine, ["A"], module_id="thcs")
    seed(memory_engine, ["B"], module_id="caohoc")
    assert items.unseen_count("thcs") == 1 and items.unseen_count("caohoc") == 1


def test_override_retire_and_reset(memory_engine):
    items, attempts = repos(memory_engine)
    a, b = seed(memory_engine, ["A", "B"])
    _answer(attempts, a, True, NOW - timedelta(days=1))
    _answer(attempts, a, True, NOW - timedelta(days=1) + timedelta(minutes=1))   # box 2
    applied = items.apply_overrides(MODULE, [
        SrsOverride(item_id=a.id, action="reset"), SrsOverride(item_id=b.id, action="retire"),
        SrsOverride(item_id="ghost", action="retire"),
    ], NOW)
    assert applied == 2   # id lạ bị bỏ qua
    with open_session(memory_engine) as s:
        state = s.get(ReviewState, a.id)
    assert state.box == 0 and state.due_at == NOW
    assert items.get(b.id).retired is True
    assert items.due_count(MODULE, NOW) == 1


def test_override_ignores_item_of_other_module(memory_engine):
    items, _ = repos(memory_engine)
    (other,) = seed(memory_engine, ["A"], module_id="caohoc")
    assert items.apply_overrides(MODULE, [SrsOverride(item_id=other.id, action="retire")], NOW) == 0
    assert items.get(other.id).retired is False


def test_srs_override_int_id_coerced(memory_engine):
    assert SrsOverride.model_validate({"item_id": 123, "action": "retire"}).item_id == "123"


def test_record_answer_updates_box_lapses_and_unknown_item_raises(memory_engine):
    _, attempts = repos(memory_engine)
    (a,) = seed(memory_engine, ["A"])
    _, s1 = _answer(attempts, a, True)
    assert (s1.box, s1.lapses, s1.prev_box) == (1, 0, 0) and s1.due_at == NOW + timedelta(days=1)
    _, s2 = _answer(attempts, a, False, NOW + timedelta(hours=1))
    assert (s2.box, s2.lapses, s2.prev_box) == (0, 1, 1)
    with pytest.raises(LookupError):
        attempts.record_answer(MODULE, "ghost", "x", True, 1, NOW, DAYS)
    with pytest.raises(LookupError):
        attempts.record_answer("other-module", a.id, "x", True, 1, NOW, DAYS)


def test_regrade_restores_previous_box_and_is_idempotent(memory_engine):
    _, attempts = repos(memory_engine)
    (a,) = seed(memory_engine, ["A"])
    for minutes in range(3):
        _answer(attempts, a, True, NOW + timedelta(minutes=minutes))   # box 3
    wrong, state = _answer(attempts, a, False, NOW + timedelta(minutes=10))
    assert state.box == 0 and state.lapses == 1
    fixed = attempts.regrade_as_correct(wrong.id, NOW + timedelta(minutes=11), DAYS)
    assert (fixed.box, fixed.lapses) == (4, 0)
    assert fixed.due_at == NOW + timedelta(minutes=11) + timedelta(days=14)
    assert attempts.get_attempt(wrong.id).correct is True
    assert attempts.regrade_as_correct(wrong.id, NOW, DAYS) is None   # lần 2: không làm gì


def test_regrade_of_older_attempt_only_fixes_the_attempt(memory_engine):
    _, attempts = repos(memory_engine)
    (a,) = seed(memory_engine, ["A"])
    wrong, _ = _answer(attempts, a, False, NOW)
    _answer(attempts, a, True, NOW + timedelta(hours=1))
    before = attempts.load_states([a.id])[a.id]
    attempts.regrade_as_correct(wrong.id, NOW + timedelta(hours=2), DAYS)
    after = attempts.load_states([a.id])[a.id]
    assert (after.box, after.lapses, after.due_at) == (before.box, before.lapses, before.due_at)


def test_recent_questions_newest_first_and_limited(memory_engine):
    items, _ = repos(memory_engine)
    for i in range(4):
        items.insert_items_dedup(MODULE, [quiz(f"Q{i}")], NOW + timedelta(minutes=i))
    assert items.recent_questions(MODULE, 2) == ["Q3", "Q2"]
