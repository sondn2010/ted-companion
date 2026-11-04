"""SOUL.md là bảng định tuyến [TED_*] -> skill: coach đủ 6 thẻ + luật MOOD, work đủ 4 thẻ."""
import pytest
from skill_sample_extraction_helper import PROFILES_DIR

COACH_TAGS = ["[TED_ONBOARDING]", "[TED_SYNC_PLAN]", "[TED_QUIZ_BATCH_REQUEST]", "[TED_EXPLAIN_MISTAKE]",
              "[TED_WRITING_SUBMISSION]", "[TED_PROGRESS_REPORT]"]
UNTANGLE_TAGS = ["[TED_UNTANGLE", "[TED_UNTANGLE_CRITIQUE]"]   # Gỡ Rối Ý Tưởng: mọi profile đều định tuyến
WORK_TAGS = ["[TED_CALENDAR_REQUEST]", "[TED_BRIEFING]", "[TED_CHEER]", "[ROCK_UPDATE]", "[TED_HEALTH_BREAK]"]


def _soul(profile: str) -> str:
    return (PROFILES_DIR / profile / "SOUL.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("profile", ["family_thcs", "family_duhoc", "family_caohoc"])
def test_coach_soul_routes_all_six_tags_and_mood_rule(profile):
    text = _soul(profile)
    assert (PROFILES_DIR / profile / "profile.kind").read_text().strip() == "coach"
    for tag in COACH_TAGS:
        assert tag in text, f"{profile} thiếu {tag}"
    assert "[MOOD:" in text


def test_work_soul_routes_its_tags():
    text = _soul("family_work")
    assert (PROFILES_DIR / "family_work" / "profile.kind").read_text().strip() == "work"
    for tag in WORK_TAGS:
        assert tag in text, tag
    assert "[MOOD:" in text


@pytest.mark.parametrize("profile", ["family_work", "family_thcs", "family_duhoc", "family_caohoc"])
def test_every_family_soul_routes_untangle_tags(profile):
    text = _soul(profile)
    for tag in UNTANGLE_TAGS:
        assert tag in text, f"{profile} thiếu {tag}"


def test_standalone_ted_soul_routes_untangle_tags():
    text = (PROFILES_DIR.parent / "hermes_profile_ted" / "SOUL.md").read_text(encoding="utf-8")
    for tag in UNTANGLE_TAGS:
        assert tag in text, tag


def test_standalone_ted_soul_routes_work_tags_and_keeps_persona():
    """Profile Ted là tập cha của Work: định tuyến đủ thẻ Work + health-break, vẫn giữ giọng Ted."""
    text = (PROFILES_DIR.parent / "hermes_profile_ted" / "SOUL.md").read_text(encoding="utf-8")
    for tag in WORK_TAGS + ["[TED_EMAIL_DIGEST]", "[TED_EISENHOWER]"]:
        assert tag in text, tag
    for skill in ("ted-health-break", "ted-briefing", "ted-eisenhower-classify", "ted-email-digest", "ted-calendar-today"):
        assert skill in text, skill
    assert 'xưng "mình"' in text and "[MOOD:IDLE]" in text   # persona gốc còn nguyên
