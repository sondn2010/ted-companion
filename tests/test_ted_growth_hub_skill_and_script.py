"""Skill ted-growth-hub: mẫu JSON khớp schema Ted, SOUL định tuyến, cài vào mọi profile (kể cả hermes_profile_ted),
và script lưu/tra cứu bền vững (idempotent, tách wellbeing, chặn path traversal)."""

import json
import os
import shutil
import subprocess
import sys
from datetime import date

import pytest
from growth_report_test_support import make_sources, seed_study_day, seed_work_day
from skill_sample_extraction_helper import COMMON_SKILLS_DIR, PROFILES_DIR, json_samples, skill_text

from src.core.gamification.growth_report_aggregation import collect_day, collect_week
from src.core.gamification.growth_report_contract_schemas import GrowthReport, ProgressReportSavedReply
from src.core.gamification.growth_report_payload_builder import build_daily_payload, build_weekly_payload

SKILL = "ted-growth-hub"
SCRIPT = COMMON_SKILLS_DIR / SKILL / "scripts" / "save_growth_report.py"
BASH = shutil.which("bash")


def _requests():
    return [s for s in json_samples(SKILL) if "kind" in s]


def _replies():
    return [s for s in json_samples(SKILL) if "saved" in s]


def test_request_samples_parse_and_cover_both_report_kinds():
    reports = [GrowthReport.model_validate(s) for s in _requests()]
    assert {r.report_kind for r in reports} == {"learning", "general"} and {r.kind for r in reports} == {"daily", "weekly"}
    assert all(r.wellbeing is None for r in reports if r.report_kind == "learning")


def test_reply_samples_parse():
    replies = [ProgressReportSavedReply.model_validate(s) for s in _replies()]
    assert [r.saved for r in replies] == [True, False] and replies[1].error


def test_sample_keys_are_subset_of_builder_keys(memory_engine):
    src = make_sources(memory_engine)
    seed_work_day(src, date(2026, 10, 21))
    seed_study_day(src, date(2026, 10, 21))
    day, week = collect_day(src, date(2026, 10, 21), set()), collect_week(src, date(2026, 10, 19), set())
    for sample in _requests():
        built = (build_daily_payload if sample["kind"] == "daily" else build_weekly_payload)(
            sample["report_kind"], sample["learner"], day if sample["kind"] == "daily" else week)
        assert set(sample) <= set(built) and set(sample.get("wellbeing", {})) <= set(built.get("wellbeing", {}))
        assert set(sample.get("counts", {})) <= set(built.get("counts", {}))


@pytest.mark.parametrize("profile", ["family_work", "family_thcs", "family_caohoc", "family_duhoc"])
def test_family_soul_routes_growth_report(profile):
    text = (PROFILES_DIR / profile / "SOUL.md").read_text(encoding="utf-8")
    assert "[TED_GROWTH_REPORT]" in text and SKILL in text


def test_standalone_ted_soul_and_readme_document_growth_hub():
    root = PROFILES_DIR.parent / "hermes_profile_ted"
    assert "[TED_GROWTH_REPORT]" in (root / "SOUL.md").read_text(encoding="utf-8")
    assert SKILL in (root / "README.md").read_text(encoding="utf-8")


def test_skill_ships_script_and_documents_query():
    assert SCRIPT.exists()
    text = skill_text(SKILL)
    assert "save_growth_report.py" in text and "tuần trước level mấy" in text and "reports/wellbeing" in text


@pytest.mark.skipif(BASH is None, reason="cần bash")
def test_work_and_coach_profiles_get_growth_skill_with_script(tmp_path):
    for profile in ("family_work", "family_thcs"):
        env = {**os.environ, "HOME": str(tmp_path), "HERMES_SKIP_PROFILE_CREATE": "1", "HERMES_ALLOW_ROOT": "1"}
        done = subprocess.run([BASH, str(PROFILES_DIR / "install_hermes_profile.sh"), profile],
                              env=env, capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr
        skill = tmp_path / ".hermes" / "profiles" / profile / "skills" / SKILL
        assert (skill / "SKILL.md").exists() and (skill / "scripts" / "save_growth_report.py").exists()


@pytest.mark.skipif(BASH is None or shutil.which("hermes") is not None, reason="cần bash và không có CLI hermes thật")
def test_standalone_ted_install_copies_growth_skill_with_script(tmp_path):
    env = {**os.environ, "HOME": str(tmp_path)}
    done = subprocess.run([BASH, str(PROFILES_DIR.parent / "hermes_profile_ted" / "install_hermes_profile.sh")],
                          env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    skill = tmp_path / ".hermes" / "profiles" / "ted" / "skills" / SKILL
    assert (skill / "SKILL.md").exists() and (skill / "scripts" / "save_growth_report.py").exists()


def _run(*args, stdin=None):
    done = subprocess.run([sys.executable, "-I", str(SCRIPT), *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", timeout=60)
    return done.returncode, json.loads(done.stdout)


def _daily(**over):
    sample = next(s for s in _requests() if s["kind"] == "daily" and s["report_kind"] == "general")
    return {**sample, **over}


def test_script_saves_files_wellbeing_index_and_is_idempotent(tmp_path):
    payload = _daily()
    for _ in range(2):   # gửi lại cùng ngày = cùng kết quả
        code, out = _run("save", "--home", str(tmp_path), stdin=json.dumps(payload))
        assert code == 0 and out["saved"] is True and out["path"] == "reports/growth/user/daily/2026-10-21.json"
    growth = tmp_path / "reports" / "growth" / "user"
    assert (growth / "daily" / "2026-10-21.md").exists() and "cấp 6" in out["memory_line"]
    assert list(json.loads((growth / "index.json").read_text(encoding="utf-8"))["daily"]) == ["2026-10-21"]
    wb = tmp_path / "reports" / "wellbeing" / "user"
    assert json.loads((wb / "daily" / "2026-10-21.json").read_text(encoding="utf-8"))["away_minutes"] == 90
    assert out["wellbeing_path"] == "reports/wellbeing/user/daily/2026-10-21.json"


def test_script_query_returns_history_oldest_first(tmp_path):
    weekly = next(s for s in _requests() if s["kind"] == "weekly")
    for week, level in (("2026-10-06", 5), ("2026-10-13", 7)):
        _run("save", "--home", str(tmp_path), stdin=json.dumps({**weekly, "week_start": week, "final_level": level}))
    code, rows = _run("query", "--home", str(tmp_path), "--learner", "user", "--kind", "weekly", "--last", "1")
    assert code == 0 and [r["final_level"] for r in rows] == [7]
    _, rows = _run("query", "--home", str(tmp_path), "--learner", "user", "--kind", "weekly", "--last", "5")
    assert [r["week_start"] for r in rows] == ["2026-10-06", "2026-10-13"]
    _, rows = _run("query", "--home", str(tmp_path), "--learner", "user", "--section", "wellbeing", "--kind", "weekly")
    assert rows and "health" in rows[0]


def test_script_learning_report_writes_no_wellbeing_and_rejects_bad_input(tmp_path):
    learning = next(s for s in _requests() if s["report_kind"] == "learning")
    code, out = _run("save", "--home", str(tmp_path), stdin=json.dumps(learning))
    assert code == 0 and "wellbeing_path" not in out and "Học tập của bin" in out["memory_line"]
    assert not (tmp_path / "reports" / "wellbeing").exists()
    for bad in ({"learner": "../evil"}, {"date": "2026-13-45"}, {"date": "../../x"}, {"report_kind": "other"}):
        code, out = _run("save", "--home", str(tmp_path), stdin=json.dumps({**learning, **bad}))
        assert code != 0 and out["saved"] is False
    code, out = _run("save", "--home", str(tmp_path), stdin="không phải json")
    assert code != 0 and out["saved"] is False
    assert not (tmp_path.parent / "evil").exists()
