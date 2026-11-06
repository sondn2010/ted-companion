"""Schema email digest / Eisenhower + prompt template work (placeholder, module.yaml)."""
import pytest
from pydantic import ValidationError

from src.engines.work.eisenhower_contract_schemas import EisenhowerClassification
from src.engines.work.email_digest_contract_schemas import EmailDigestResponse, EmailItem
from src.modules_runtime.prompt_template_renderer import render_prompt
from tests.skill_sample_extraction_helper import REPO_ROOT

WORK_DIR = REPO_ROOT / "modules" / "work"


def test_email_item_accepts_from_alias_and_nulls():
    item = EmailItem.model_validate({"from": "A <a@x.com>", "subject": None, "summary": "s", "priority": "low"})
    assert item.sender == "A <a@x.com>" and item.subject == "" and item.reason == ""


def test_email_item_rejects_bad_priority_and_negative_total():
    with pytest.raises(ValidationError):
        EmailItem.model_validate({"from": "a", "priority": "urgent"})
    with pytest.raises(ValidationError):
        EmailDigestResponse.model_validate({"emails": [], "total_unread": -1})


def test_email_digest_defaults():
    reply = EmailDigestResponse.model_validate({})
    assert reply.emails == [] and reply.total_unread == 0


@pytest.mark.parametrize("quadrant", [1, 2, 3, 4])
def test_eisenhower_valid_quadrants(quadrant):
    assert EisenhowerClassification.model_validate({"quadrant": quadrant}).reason == ""


@pytest.mark.parametrize("quadrant", [0, 5, "x"])
def test_eisenhower_rejects_out_of_range(quadrant):
    with pytest.raises(ValidationError):
        EisenhowerClassification.model_validate({"quadrant": quadrant, "reason": "r"})


def test_briefing_prompt_has_slot_and_fenced_emails_and_missing_values_do_not_raise():
    template = (WORK_DIR / "prompts" / "briefing.md").read_text(encoding="utf-8")
    assert "{{slot}}" in template and "<emails>\n{{emails}}\n</emails>" in template
    legacy = render_prompt(template, {"now": "n", "tasks": "t", "events": "e", "rocks": "r"})
    assert "{{slot}}" in legacy   # giá trị thiếu giữ nguyên, không lỗi
    full = render_prompt(template, {"now": "n", "slot": "midday", "tasks": "t", "events": "e", "emails": "m", "rocks": "r"})
    assert "{{" not in full and "Buổi: midday" in full


def test_request_prompts_render_placeholders():
    digest = (WORK_DIR / "prompts" / "email-digest-request.md").read_text(encoding="utf-8")
    assert render_prompt(digest, {"since": "S", "tz": "Z", "max": 8}).strip() == "[TED_EMAIL_DIGEST] since=S tz=Z max=8"
    eis = (WORK_DIR / "prompts" / "eisenhower-classify.md").read_text(encoding="utf-8")
    assert "<idea>\nviệc\n</idea>" in render_prompt(eis, {"today": "2026-10-21", "idea": "việc"})
