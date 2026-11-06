"""Payload báo cáo tăng trưởng: learning ≠ general, khối wellbeing tách riêng, chỉ số tổng hợp (không nội dung)."""

import json
from datetime import date

from growth_report_test_support import SECRET_TITLE, make_sources, seed_study_day, seed_work_day

from src.core.gamification.growth_report_aggregation import collect_day, collect_week
from src.core.gamification.growth_report_contract_schemas import GrowthReport
from src.core.gamification.growth_report_payload_builder import (
    build_daily_payload, build_weekly_payload, wellbeing_block_of_day)

DAY = date(2026, 10, 21)
WEEK = date(2026, 10, 19)   # thứ Hai chứa DAY


def _seeded(engine):
    src = make_sources(engine)
    seed_work_day(src, DAY)
    seed_study_day(src, DAY)
    return src


def test_general_daily_has_everything_and_validates(memory_engine):
    agg = collect_day(_seeded(memory_engine), DAY, set())
    payload = build_daily_payload("general", "user", agg)
    GrowthReport.model_validate(payload)
    assert {"level", "pct", "xp_day", "decayed", "stats", "counts", "wellbeing"} <= set(payload)
    assert payload["counts"]["tasks_done"] == 1 and payload["counts"]["quiz_answered"] == 3
    assert payload["wellbeing"]["away_minutes"] == 30 and payload["wellbeing"]["app_on_minutes"] == 100
    assert "energy" in payload["stats"]


def test_learning_daily_excludes_work_and_wellbeing_numbers(memory_engine):
    agg = collect_day(_seeded(memory_engine), DAY, set())
    payload = build_daily_payload("learning", "bin", agg)
    GrowthReport.model_validate(payload)
    assert set(payload["counts"]) == {"quiz_answered", "quiz_correct", "agenda_done", "writing_graded",
                                      "study_meetings", "study_meeting_minutes"}
    assert set(payload["stats"]) <= {"data", "learning"}
    for forbidden in ("level", "pct", "xp_day", "wellbeing", "decayed"):
        assert forbidden not in payload
    assert payload["coach_xp"] == 2 * 3 + 3 and payload["report_kind"] == "learning"


def test_wellbeing_block_is_separable_and_matches_repo_export(memory_engine):
    src = _seeded(memory_engine)
    payload = build_daily_payload("general", "user", collect_day(src, DAY, set()))
    block = payload["wellbeing"]
    raw = src.wellbeing.export_range(DAY, DAY)[0]
    assert (block["away_minutes"], block["breaks"], block["outings"]) == (raw["away_minutes"], raw["breaks_taken"], raw["outings"])
    assert block == wellbeing_block_of_day(collect_day(src, DAY, set()))
    without = {k: v for k, v in payload.items() if k != "wellbeing"}
    GrowthReport.model_validate(without)   # bỏ khối vẫn là báo cáo hợp lệ


def test_weekly_general_and_learning(memory_engine):
    src = _seeded(memory_engine)
    agg = collect_week(src, WEEK, set())
    general = build_weekly_payload("general", "user", agg)
    learning = build_weekly_payload("learning", "bin", agg)
    GrowthReport.model_validate(general)
    GrowthReport.model_validate(learning)
    assert general["xp_earned"] > 0 and "wellbeing" in general and general["wellbeing"]["away_minutes"] == 30
    assert "wellbeing" not in learning and "xp_earned" not in learning and learning["counts"]["quiz_answered"] == 3
    assert learning["active_days"] == 1


def test_payloads_never_contain_titles_or_text(memory_engine):
    src = _seeded(memory_engine)
    blob = json.dumps([
        build_daily_payload("general", "user", collect_day(src, DAY, set())),
        build_daily_payload("learning", "bin", collect_day(src, DAY, set())),
        build_weekly_payload("general", "user", collect_week(src, WEEK, set()))], ensure_ascii=False)
    assert SECRET_TITLE not in blob


def test_learning_badges_only_in_learning_report(memory_engine):
    src = _seeded(memory_engine)
    from datetime import datetime, timezone
    src.unlocks.add("quiz_first", WEEK.isoformat())
    src.unlocks.add("focus_day_silver", WEEK.isoformat())
    now = datetime.now(timezone.utc).astimezone().date()
    agg_day = collect_day(src, now, {"quiz_first"})   # huy hiệu vừa mở "hôm nay"
    assert agg_day.badges_new == ["focus_day_silver", "quiz_first"] and agg_day.learning_badges_new == ["quiz_first"]
    learning = build_daily_payload("learning", "bin", agg_day)
    general = build_daily_payload("general", "user", agg_day)
    assert learning["badges_new"] == ["quiz_first"] and len(general["badges_new"]) == 2
