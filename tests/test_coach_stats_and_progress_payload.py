import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.engines.coach.coach_stats_builder import streak_days, subject_of
from src.engines.coach.coach_stats_collector import collect_progress_payload, collect_sync_stats
from coach_test_support import DAYS, MODULE, TZ, repos, seed

SAMPLE = Path(__file__).resolve().parent.parent / "hermes_profiles" / "_shared" / "skills" / "ted-progress-report" / "SKILL.md"
# 10:00 giờ VN ngày 2026-10-19 (03:00 UTC)
T0 = datetime(2026, 10, 19, 3, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 19)


def _ans(attempts, item, correct, when, secs=30):
    return attempts.record_answer(MODULE, item.id, "a", correct, secs, when, DAYS)


def _shape(value):
    """Cấu trúc khoá (đệ quy) của JSON mẫu, để so với payload Ted sinh ra."""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return "scalar"   # item_id: mẫu dùng số, Ted dùng uuid chuỗi → chỉ so cấu trúc khoá


def test_subject_is_topic_prefix():
    assert subject_of("hsk.hsk3-vocab") == "hsk" and subject_of("english.conditionals") == "english"
    assert subject_of("") == "general" and subject_of("single") == "single"


def test_streak_counts_back_and_breaks_on_gap():
    days = {TODAY, TODAY - timedelta(1), TODAY - timedelta(2), TODAY - timedelta(4)}
    assert streak_days(days, TODAY) == 3
    assert streak_days({TODAY - timedelta(1), TODAY - timedelta(2)}, TODAY) == 2   # hôm nay chưa học
    assert streak_days({TODAY - timedelta(2)}, TODAY) == 0
    assert streak_days(set(), TODAY) == 0


def test_no_attempts_gives_no_report(memory_engine):
    _, attempts = repos(memory_engine)
    assert collect_progress_payload(attempts, MODULE, "con", TODAY, T0, TZ) is None


def test_progress_payload_matches_skill_sample_shape_and_values(memory_engine):
    items, attempts = repos(memory_engine)
    en = seed(memory_engine, ["E1", "E2", "E3"], topic="english.present-perfect")
    hsk = seed(memory_engine, ["H1"], topic="hsk.hsk3-vocab")
    for i, item in enumerate(en):   # 1 đúng, 2 sai → chủ đề yếu
        _ans(attempts, item, i == 0, T0 + timedelta(minutes=i))
    _ans(attempts, hsk[0], True, T0 + timedelta(minutes=5), secs=90)
    items.flag_item(en[1].id, "đáp án sai")
    payload = collect_progress_payload(attempts, MODULE, "con", TODAY, T0 + timedelta(hours=8), TZ)

    sample = json.loads(re.search(r"<json>\s*(\{\s*\"date\".*?)\s*</json>", SAMPLE.read_text(encoding="utf-8"), re.S).group(1))
    assert _shape({k: v for k, v in payload.items()}) == _shape(sample)
    assert (payload["date"], payload["learner"], payload["module"]) == ("2026-10-19", "con", MODULE)
    by_subject = {s["subject"]: s for s in payload["subjects"]}
    assert by_subject["english"]["answered"] == 3 and by_subject["english"]["correct"] == 1
    assert by_subject["english"]["weak_topics"] == [{"topic": "english.present-perfect", "correct": 1, "total": 3}]
    assert by_subject["english"]["new_items"] == 3 and by_subject["hsk"]["weak_topics"] == []
    assert payload["flagged"] == [{"item_id": en[1].id, "question": "E2", "reason": "đáp án sai"}]
    assert payload["study_minutes"] == round((30 * 3 + 90) / 60) and payload["streak_days"] == 1


def test_new_items_only_counts_first_ever_attempt_that_day(memory_engine):
    _, attempts = repos(memory_engine)
    a, b = seed(memory_engine, ["A", "B"])
    _ans(attempts, a, True, T0 - timedelta(days=1))    # đã hỏi hôm qua
    _ans(attempts, a, True, T0)
    _ans(attempts, b, True, T0)
    payload = collect_progress_payload(attempts, MODULE, "con", TODAY, T0, TZ)
    assert payload["subjects"][0]["new_items"] == 1 and payload["streak_days"] == 2


def test_mastered_means_reached_box_4_that_day(memory_engine):
    _, attempts = repos(memory_engine)
    quick, old = seed(memory_engine, ["Quick", "Old"])
    for i in range(4):   # quick: 0→4 trong hôm nay
        _ans(attempts, quick, True, T0 + timedelta(minutes=i))
    for i in range(4):   # old: lên hộp 4 từ hôm qua, hôm nay chỉ lên 5
        _ans(attempts, old, True, T0 - timedelta(days=1, minutes=-i))
    _ans(attempts, old, True, T0 + timedelta(minutes=10))
    payload = collect_progress_payload(attempts, MODULE, "con", TODAY, T0, TZ)
    assert payload["subjects"][0]["mastered_items"] == 1


def test_report_day_uses_local_timezone_boundary(memory_engine):
    _, attempts = repos(memory_engine)
    (a,) = seed(memory_engine, ["A"])
    late = datetime(2026, 10, 19, 17, 30, tzinfo=timezone.utc)   # 00:30 ngày 20 giờ VN
    _ans(attempts, a, True, late)
    assert collect_progress_payload(attempts, MODULE, "con", date(2026, 10, 19), late, TZ) is None
    assert collect_progress_payload(attempts, MODULE, "con", date(2026, 10, 20), late, TZ)["subjects"][0]["answered"] == 1


def test_sync_stats_shape_weak_topics_and_counts(memory_engine):
    items, attempts = repos(memory_engine)
    weak = seed(memory_engine, [f"W{i}" for i in range(4)], topic="english.conditionals")
    fine = seed(memory_engine, ["F0", "F1"], topic="math.inequalities")
    seed(memory_engine, ["U0", "U1", "U2"], topic="hsk.hsk3-vocab")   # chưa hỏi
    now = T0 + timedelta(hours=9)
    for i, item in enumerate(weak):
        _ans(attempts, item, i == 0, T0 + timedelta(minutes=i))   # 1/4 đúng
    for i, item in enumerate(fine):
        _ans(attempts, item, True, T0 - timedelta(days=3, minutes=i))
    _ans(attempts, fine[0], False, T0 - timedelta(days=30))   # ngoài cửa sổ 7 ngày
    stats = collect_sync_stats(items, attempts, MODULE, now, TZ)
    assert stats["last7_answered"] == 6 and stats["last7_correct"] == 3
    assert stats["weak_topics"] == [{"topic": "english.conditionals", "correct": 1, "total": 4}]
    assert stats["unseen_items"] == 3 and stats["due_reviews"] >= 3
    assert stats["streak_days"] == 1
    assert set(stats) == {"last7_answered", "last7_correct", "weak_topics", "due_reviews", "unseen_items", "streak_days"}


def test_weak_topics_need_two_attempts_and_are_capped_at_five(memory_engine):
    items, attempts = repos(memory_engine)
    for n in range(7):
        topic = f"s.t{n}"
        pair = seed(memory_engine, [f"T{n}a", f"T{n}b"], topic=topic)
        for item in pair:
            _ans(attempts, item, False, T0)
    (single,) = seed(memory_engine, ["Single"], topic="s.single")
    _ans(attempts, single, False, T0)   # chỉ 1 lượt → không phải chủ đề yếu
    stats = collect_sync_stats(items, attempts, MODULE, T0 + timedelta(hours=1), TZ)
    assert len(stats["weak_topics"]) == 5 and "s.single" not in {w["topic"] for w in stats["weak_topics"]}
