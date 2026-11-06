"""Unit tests cho skill ted-parent-reporter & script parent_reporter.py."""

import json
import subprocess
import sys
from pathlib import Path
import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "hermes_profiles"
    / "_common"
    / "skills"
    / "ted-parent-reporter"
    / "scripts"
    / "parent_reporter.py"
)


def _run_cli(*args, stdin=""):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc


def test_parent_reporter_save_and_query(tmp_path):
    home = tmp_path / "hermes_home"
    home.mkdir()

    payload = {
        "kind": "daily_activity",
        "date": "2026-10-22",
        "learner": "uyen",
        "study_minutes": 80.0,
        "distraction_minutes": 15.0,
        "neutral_minutes": 10.0,
        "focus_percentage": 84.2,
        "self_corrected_count": 2,
        "breach_count": 0,
        "unsafe_attempts": 0,
        "status": "good",
        "top_apps": [
            {"app": "Microsoft Word", "minutes": 45.0},
            {"app": "GeoGebra", "minutes": 35.0},
            {"app": "TikTok", "minutes": 15.0}
        ]
    }

    # 1. Test Save
    res = _run_cli("save", "--home", str(home), stdin=json.dumps(payload))
    assert res.returncode == 0
    saved_meta = json.loads(res.stdout.strip())
    assert saved_meta["saved"] is True
    assert "reports/activity/uyen/daily/2026-10-22.json" in saved_meta["path"]

    # Verify JSON and MD files exist on disk
    json_file = home / "reports" / "activity" / "uyen" / "daily" / "2026-10-22.json"
    md_file = home / "reports" / "activity" / "uyen" / "daily" / "2026-10-22.md"
    assert json_file.exists()
    assert md_file.exists()

    md_content = md_file.read_text(encoding="utf-8")
    assert "**Thời gian học sâu:** 80.0 phút" in md_content
    assert "Microsoft Word" in md_content

    # Verify USER.md memory was updated
    user_md = home / "memories" / "USER.md"
    assert user_md.exists()
    assert "Thói quen học tập của uyen:" in user_md.read_text(encoding="utf-8")

    # 2. Test Format Telegram
    res_fmt = _run_cli(
        "format-telegram",
        "--home", str(home),
        "--learner", "uyen",
        "--date", "2026-10-22",
        "--type", "summary"
    )
    assert res_fmt.returncode == 0
    msg = res_fmt.stdout
    assert "NHẬT KÝ HỌC TẬP TỐI NAY CỦA UYÊN" in msg
    assert "80.0 phút" in msg
    assert "Lời nhắn từ Ted" in msg

    # 3. Test Query
    res_q = _run_cli("query", "--home", str(home), "--learner", "uyen", "--last", "5")
    assert res_q.returncode == 0
    query_data = json.loads(res_q.stdout)
    assert query_data["learner"] == "uyen"
    assert len(query_data["items"]) == 1
    assert query_data["items"][0]["date"] == "2026-10-22"


def test_parent_reporter_prevents_path_traversal(tmp_path):
    home = tmp_path / "hermes_home"
    home.mkdir()

    bad_payload = {
        "kind": "daily_activity",
        "date": "../../../etc/passwd",
        "learner": "uyen/../../root",
        "study_minutes": 10
    }

    res = _run_cli("save", "--home", str(home), stdin=json.dumps(bad_payload))
    assert res.returncode != 0
    data = json.loads(res.stdout)
    assert data["saved"] is False
