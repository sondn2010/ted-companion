"""Hợp đồng sống: mọi mẫu <json> trong 6 skill dùng chung phải khớp schema pydantic phía Ted."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from skill_sample_extraction_helper import json_samples, sample_with_key, skill_text

from src.engines.coach.coach_quiz_writing_report_schemas import (
    ONBOARDING_DONE_RE, ProgressReportSavedReply, QuizBatchResponse, WritingGradeResult)
from src.engines.coach.coach_stats_builder import build_progress_payload
from src.engines.coach.coach_sync_plan_schemas import SyncPlanResponse
from src.engines.work.calendar_contract_schemas import CalendarResponse
from src.engines.work.eisenhower_contract_schemas import EisenhowerClassification
from src.engines.work.email_digest_contract_schemas import EmailDigestResponse


def test_plan_sync_full_sample_parses_with_all_five_agenda_kinds_valid():
    sample = sample_with_key("ted-plan-sync", "agenda")
    reply = SyncPlanResponse.model_validate(sample)
    payload = reply.payload
    assert not reply.needs_onboarding and payload is not None
    assert len(payload.agenda) == len(sample["agenda"])   # không mục nào bị bỏ lặng lẽ
    assert payload.policy is not None and payload.policy.leitner_days[0] == 0.007
    assert [m.id for m in payload.milestones] == ["ms-hsk3"]
    assert payload.checklist[0].status == "todo" and payload.srs_overrides[0].item_id == "123"
    assert next(a for a in payload.agenda if a.kind == "writing").prompt


def test_plan_sync_needs_onboarding_sample():
    reply = SyncPlanResponse.model_validate({"needs_onboarding": True})
    assert reply.needs_onboarding and reply.payload is None
    assert '{"needs_onboarding":true}' in skill_text("ted-plan-sync")


def test_quiz_generator_sample_keeps_mcq_short_and_step():
    sample = sample_with_key("ted-quiz-generator", "items")
    reply = QuizBatchResponse.model_validate(sample)
    assert [i.type for i in reply.items] == ["mcq", "short", "step"]
    assert len(reply.items[2].hints) == 3


def test_writing_grader_sample_parses():
    sample = sample_with_key("ted-writing-grader", "overall")
    result = WritingGradeResult.model_validate(sample)
    assert result.overall == 6.25 and len(result.errors) == 1 and result.next_focus


def test_progress_report_reply_samples_parse():
    replies = [s for s in json_samples("ted-progress-report") if "saved" in s]
    assert replies
    parsed = [ProgressReportSavedReply.model_validate(s) for s in replies]
    assert any(p.saved and p.path.startswith("reports/progress/") for p in parsed)
    assert any(not p.saved and p.error for p in parsed)


def test_progress_report_request_keys_are_subset_of_ted_payload_keys():
    sample = sample_with_key("ted-progress-report", "subjects")
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    start = datetime(2026, 10, 19, tzinfo=tz).astimezone(timezone.utc)
    from src.engines.coach.coach_data_models import Attempt, QuizItem
    item = QuizItem(id="i1", module_id="thcs", topic="english.conditionals", type="short", question="q",
                    answer="a", created_at=start, flagged=True, flag_reason="đáp án sai")
    attempt = Attempt(module_id="thcs", item_id="i1", correct=True, response_secs=30, answered_at=start)
    ours = build_progress_payload(date(2026, 10, 19), "con", "thcs", [attempt], {"i1": item}, {}, {"i1"}, 1, start, start)
    assert set(sample) <= set(ours), set(sample) - set(ours)
    assert set(sample["subjects"][0]) <= set(ours["subjects"][0])
    assert set(sample["flagged"][0]) <= set(ours["flagged"][0])


def test_onboarding_final_block_matches_done_regex():
    text = skill_text("ted-learning-onboarding")
    match = ONBOARDING_DONE_RE.search(text)
    assert match is not None and '"onboarding":"done"' in match.group(1).replace(" ", "")


def test_work_calendar_skill_sample_parses():
    sample = sample_with_key("ted-calendar-today", "events")
    assert CalendarResponse.model_validate(sample).events


def test_email_digest_skill_samples_parse():
    reply = EmailDigestResponse.model_validate(sample_with_key("ted-email-digest", "emails"))
    assert reply.emails[0].priority == "important" and reply.emails[0].sender and reply.total_unread == 12
    assert EmailDigestResponse.model_validate({"emails": [], "total_unread": 0}).emails == []
    assert '{"error": "no_gmail_access"}' in skill_text("ted-email-digest")


def test_eisenhower_skill_sample_parses_and_embeds_four_quadrant_rules():
    result = EisenhowerClassification.model_validate(sample_with_key("ted-eisenhower-classify", "quadrant"))
    assert result.quadrant == 2 and result.reason
    text = skill_text("ted-eisenhower-classify")
    for label in ("Làm ngay", "Lên lịch", "Giao việc", "Loại bỏ"):
        assert label in text


def test_idea_untangle_critique_sample_parses_verbatim():
    from src.core.idea_untangle.untangle_critique_contract_schemas import UntangleCritique
    sample = sample_with_key("ted-idea-untangle", "summary")
    critique = UntangleCritique.model_validate(sample)
    assert len(critique.flow_steps) == len(sample["flow_steps"])      # không bước nào bị cắt lặng lẽ
    assert critique.logic_gaps[0].step == 2 and critique.logic_gaps[0].question
    assert critique.next_step and critique.assumptions and critique.new_angles


def test_health_break_skill_sample_parses_and_reads_wellbeing_history():
    from src.core.gamification.health_break_contract_schema import HealthBreakSuggestion
    suggestion = HealthBreakSuggestion.model_validate(sample_with_key("ted-health-break", "action_id"))
    assert suggestion.kind in ("move", "water", "eyes", "breath", "posture") and suggestion.text_vi and suggestion.text_en
    text = skill_text("ted-health-break")
    assert "[TED_HEALTH_BREAK]" in text and "query" in text and "--section wellbeing" in text
