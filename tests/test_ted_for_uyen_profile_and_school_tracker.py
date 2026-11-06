"""Profile ted_for_uyen (buổi tối từ 17:00) + skill ted-school-tracker của family_thcs + cầu nối giữa hai bên."""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from skill_sample_extraction_helper import COMMON_SKILLS_DIR, PROFILES_DIR

UYEN_DIR = PROFILES_DIR / "hermes_profile_ted_for_uyen"
TRACKER = PROFILES_DIR / "family_thcs" / "skills" / "ted-school-tracker" / "scripts" / "school_tracker.py"
PLANNER = UYEN_DIR / "skills" / "uyen-evening-planner" / "scripts" / "plan_evening_timeline.py"
BRIDGE = UYEN_DIR / "skills" / "uyen-thcs-bridge" / "scripts" / "ask_family_thcs.py"
SETTINGS = UYEN_DIR / "knowledge" / "evening-settings.json"
BASH = shutil.which("bash")


def _run(script: Path, *args, stdin: str = "", env: dict | None = None) -> dict:
    done = subprocess.run([sys.executable, str(script), *args], input=stdin, capture_output=True, text=True,
                          encoding="utf-8", timeout=60, env=env)
    return json.loads(done.stdout.strip().splitlines()[-1])


# ---- family_thcs: sổ lịch học thêm + bài tập ----
def test_school_tracker_status_splits_pending_and_overdue(tmp_path):
    home = str(tmp_path)
    cls = {"id": "cls-toan", "subject": "toan", "title": "Toán thầy An", "weekdays": [4], "start": "18:00",
           "end": "19:30", "travel_minutes": 15}
    assert _run(TRACKER, "set-class", "--home", home, stdin=json.dumps(cls))["ok"]
    hws = [{"subject": "van", "title": "Đoạn văn", "source": "school", "assigned": "2026-10-22", "due": "2026-10-24", "minutes": 40},
           {"subject": "anh", "title": "Unit 3", "source": "school", "assigned": "2026-10-19", "due": "2026-10-21"},
           {"subject": "toan", "title": "Bài 1-5", "source": "extra_class", "class_id": "cls-toan", "assigned": "2026-10-22", "due": "2026-10-23"}]
    added = _run(TRACKER, "add-homework", "--home", home, stdin=json.dumps(hws))["added"]
    assert [h["id"] for h in added] == ["hw-2026-10-22-1", "hw-2026-10-19-1", "hw-2026-10-22-2"]

    st = _run(TRACKER, "status", "--home", home, "--date", "2026-10-22")   # Thứ Năm (ISO 4)
    assert [c["id"] for c in st["extra_classes_today"]] == ["cls-toan"]
    assert [h["id"] for h in st["homework_pending"]] == ["hw-2026-10-22-2", "hw-2026-10-22-1"]   # hạn gần trước
    assert [h["id"] for h in st["homework_overdue"]] == ["hw-2026-10-19-1"]
    assert st["summary"] == {"classes": 1, "pending": 2, "overdue": 1, "pending_minutes": 100,
                          "by_source": {"school": 2, "extra_class": 1}}
    assert (st["homework_pending"][0]["source"], st["homework_pending"][0]["class_id"]) == ("extra_class", "cls-toan")

    assert _run(TRACKER, "update-homework", "--home", home, "--id", "hw-2026-10-19-1", "--status", "done")["ok"]
    st = _run(TRACKER, "status", "--home", home, "--date", "2026-10-23")   # Thứ Sáu: không học thêm
    assert st["extra_classes_today"] == [] and st["homework_overdue"] == []

    # lưu bền trong SQLite của profile family_thcs (không phải file JSON)
    with sqlite3.connect(tmp_path / "data" / "school.db") as db:
        assert db.execute("SELECT weekdays FROM extra_classes WHERE id = 'cls-toan'").fetchone() == ("4",)
        assert db.execute("SELECT status FROM homework WHERE id = 'hw-2026-10-19-1'").fetchone() == ("done",)
    assert not (tmp_path / "knowledge").exists()


def test_school_tracker_add_is_atomic_and_upsert_class(tmp_path):
    home = str(tmp_path)
    bad_batch = [{"subject": "van", "title": "ok", "source": "school"},
                 {"subject": "toan", "title": "x", "source": "extra_class", "class_id": "cls-khong-co"}]
    assert _run(TRACKER, "add-homework", "--home", home, stdin=json.dumps(bad_batch))["ok"] is False
    assert _run(TRACKER, "status", "--home", home, "--date", "2026-10-22")["summary"]["pending"] == 0
    cls = {"id": "cls-anh", "subject": "anh", "title": "Anh", "weekdays": [1], "start": "17:30", "end": "19:00"}
    _run(TRACKER, "set-class", "--home", home, stdin=json.dumps(cls))
    _run(TRACKER, "set-class", "--home", home, stdin=json.dumps({**cls, "weekdays": [2, 6]}))
    assert _run(TRACKER, "status", "--home", home, "--date", "2026-10-24")["extra_classes_today"][0]["weekdays"] == [2, 6]
    assert _run(TRACKER, "remove-class", "--home", home, "--id", "cls-anh")["ok"]
    assert _run(TRACKER, "update-homework", "--home", home, "--id", "hw-x", "--status", "done")["ok"] is False


@pytest.mark.parametrize("bad", [{"id": "../x", "subject": "a", "title": "b", "weekdays": [1], "start": "18:00", "end": "19:00"},
                                 {"id": "c", "subject": "a", "title": "b", "weekdays": [8], "start": "18:00", "end": "19:00"},
                                 {"id": "c", "subject": "a", "title": "b", "weekdays": [1], "start": "19:00", "end": "18:00"}])
def test_school_tracker_rejects_bad_class(tmp_path, bad):
    assert _run(TRACKER, "set-class", "--home", str(tmp_path), stdin=json.dumps(bad))["ok"] is False


def test_homework_requires_source_and_class_link_survives_class_update(tmp_path):
    home = str(tmp_path)
    no_source = {"subject": "van", "title": "Đoạn văn"}
    assert "source" in _run(TRACKER, "add-homework", "--home", home, stdin=json.dumps(no_source))["error"]
    school_with_class = {"subject": "van", "title": "x", "source": "school", "class_id": "cls-toan"}
    assert _run(TRACKER, "add-homework", "--home", home, stdin=json.dumps(school_with_class))["ok"] is False

    cls = {"id": "cls-toan", "subject": "toan", "title": "Toán", "weekdays": [2], "start": "18:00", "end": "19:30"}
    _run(TRACKER, "set-class", "--home", home, stdin=json.dumps(cls))
    hw = {"subject": "toan", "title": "Đề 3", "source": "extra_class", "class_id": "cls-toan", "assigned": "2026-10-22"}
    hw_id = _run(TRACKER, "add-homework", "--home", home, stdin=json.dumps(hw))["added"][0]["id"]

    def class_of_hw():
        st = _run(TRACKER, "status", "--home", home, "--date", "2026-10-22")
        return next(h["class_id"] for h in st["homework_pending"] if h["id"] == hw_id)

    _run(TRACKER, "set-class", "--home", home, stdin=json.dumps({**cls, "start": "17:30"}))   # sửa lớp: giữ liên kết
    assert class_of_hw() == "cls-toan"
    _run(TRACKER, "remove-class", "--home", home, "--id", "cls-toan")   # xoá lớp: bài còn, mất liên kết
    assert class_of_hw() is None


def test_thcs_soul_routes_school_status_read_only():
    """Bố mẹ cập nhật sổ qua Telegram; máy (Ted của Uyên) chỉ đọc -> không có thẻ ghi."""
    soul = (PROFILES_DIR / "family_thcs" / "SOUL.md").read_text(encoding="utf-8")
    skill = (TRACKER.parent.parent / "SKILL.md").read_text(encoding="utf-8")
    for token in ("[TED_SCHOOL_STATUS]", "ted-school-tracker", "Telegram"):
        assert token in soul, token
    assert "[TED_HOMEWORK_UPDATE]" not in soul + skill


def test_uyen_bridge_has_no_write_commands():
    help_text = subprocess.run([sys.executable, str(BRIDGE), "--help"], capture_output=True, text=True,
                               encoding="utf-8").stdout
    assert "status" in help_text and "done" not in help_text.split("Kênh gửi")[0].replace("Không có lệnh ghi", "")
    for cmd in ("done", "add"):
        assert subprocess.run([sys.executable, str(BRIDGE), cmd], capture_output=True).returncode != 0


# ---- ted_for_uyen: lịch buổi tối + nhắc nhở ----
STATUS = {"extra_classes_today": [{"id": "cls-toan", "title": "Toán", "start": "18:00", "end": "19:30",
                                   "travel_minutes": 15}],
          "homework_overdue": [{"id": "hw-old", "subject": "anh", "title": "Unit 3", "due": "2026-10-21", "minutes": 20,
                                "source": "school"}],
          "homework_pending": [{"id": "hw-new", "subject": "toan", "title": "Đề 3", "due": "2026-10-23", "minutes": 60,
                                "source": "extra_class", "class_id": "cls-toan"}]}


def _blocks(plan: dict, kind: str) -> list:
    return [(b["start"], b["end"]) for b in plan["blocks"] if b["kind"] == kind]


def test_planner_fits_homework_around_rest_class_and_dinner():
    plan = _run(PLANNER, "--settings", str(SETTINGS), "--now", "17:00", stdin=json.dumps(STATUS))
    assert plan["ok"] and plan["stats"]["fits_tonight"]
    assert _blocks(plan, "rest") == [("17:00", "17:15")]
    assert _blocks(plan, "class") == [("17:45", "19:45")]            # 18:00-19:30 + 15' đi/về
    assert _blocks(plan, "dinner") == [("18:45", "19:30")]
    focus = [b for b in plan["blocks"] if b["kind"] == "focus"]
    assert focus[0]["homework_id"] == "hw-old" and focus[0]["overdue"]   # tồn đọng làm trước
    assert focus[0]["source"] == "school" and focus[-1]["source"] == "extra_class"
    assert (focus[0]["start"], focus[0]["end"]) == ("17:15", "17:35")
    assert all(b["start"] >= "19:45" for b in focus[1:])               # không đè giờ học thêm
    assert sum(int(b["end"][:2]) * 60 + int(b["end"][3:]) - int(b["start"][:2]) * 60 - int(b["start"][3:])
               for b in focus) == 80
    reminders = {r["kind"]: r for r in plan["reminders"]}
    assert reminders["class_leave"]["at"] == "17:35" and reminders["class_leave"]["in_minutes"] == 35
    assert reminders["wind_down"]["at"] == "21:15" and reminders["screen_off"]["at"] == "21:30"
    assert reminders["bedtime"]["at"] == "22:00"


def test_planner_late_start_reports_unscheduled_and_drops_past_reminders():
    big = {**STATUS, "homework_pending": [{"id": "hw-big", "subject": "toan", "title": "Đề cương", "minutes": 240}]}
    plan = _run(PLANNER, "--settings", str(SETTINGS), "--now", "20:00", stdin=json.dumps(big))
    assert not plan["stats"]["fits_tonight"]
    assert plan["unscheduled"][0]["id"] == "hw-big"
    assert all(r["at"] >= "20:00" for r in plan["reminders"])
    assert all(b["end"] <= "21:30" for b in plan["blocks"] if b["kind"] == "focus")


def test_planner_weekday_screen_off_2130_and_weekend_override(tmp_path):
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert settings["screen_off"] == "21:30"   # ngày thường: bố mẹ yêu cầu tắt máy 21:30
    settings["weekend_overrides"] = {"screen_off": "22:00", "bedtime": "22:30"}
    path = tmp_path / "s.json"
    path.write_text(json.dumps(settings), encoding="utf-8")

    def screen_off(weekday: int) -> str:
        plan = _run(PLANNER, "--settings", str(path), "--now", "17:00", stdin=json.dumps({"weekday": weekday}))
        return next(r["at"] for r in plan["reminders"] if r["kind"] == "screen_off")

    assert screen_off(4) == "21:30" and screen_off(6) == "22:00" and screen_off(7) == "22:00"


def test_planner_without_status_still_plans_wind_down():
    plan = _run(PLANNER, "--settings", str(SETTINGS), "--now", "17:00")
    assert plan["ok"] and [b for b in plan["blocks"] if b["kind"] == "focus"] == []
    assert {"wind_down", "screen_off", "bedtime"} <= {r["kind"] for r in plan["reminders"]}


# ---- cầu nối sang family_thcs (kênh HTTP, server giả) ----
def test_bridge_http_sends_status_tag_and_extracts_last_json_block(tmp_path):
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["auth"] = self.headers.get("Authorization")
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            reply = 'note <json>{"draft":1}</json> final <json>{"ok": true, "summary": {"pending": 2}}</json>'
            data = json.dumps({"choices": [{"message": {"content": reply}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        (tmp_path / ".env").write_text(f"THCS_API_URL=http://127.0.0.1:{server.server_port}\nTHCS_API_KEY=k123\n")
        env = {k: v for k, v in os.environ.items() if not k.startswith("THCS_")}
        result = _run(BRIDGE, "status", "--date", "2026-10-22", "--home", str(tmp_path), env=env)
    finally:
        server.shutdown()
    assert result == {"ok": True, "summary": {"pending": 2}}
    assert seen["auth"] == "Bearer k123"
    assert seen["body"]["messages"][0]["content"] == "[TED_SCHOOL_STATUS] date=2026-10-22 learner=uyen"


# ---- SOUL + installer ----
def test_uyen_soul_keeps_ted_persona_and_routes_student_skills():
    text = (UYEN_DIR / "SOUL.md").read_text(encoding="utf-8")
    for token in ("[MOOD:IDLE]", "[TED_UNTANGLE", "[TED_UNTANGLE_CRITIQUE]", "[TED_GROWTH_REPORT]",
                  "[TED_HEALTH_BREAK]", "uyen-thcs-bridge", "uyen-evening-planner", "17:00"):
        assert token in text, token
    assert "[TED_EMAIL_DIGEST]" not in text and "[TED_CALENDAR_REQUEST]" not in text


@pytest.mark.skipif(BASH is None, reason="cần bash")
def test_uyen_bash_install_skills_and_keeps_user_data(tmp_path):
    keep = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d and shutil.which("hermes", path=d) is None]
    env = {**os.environ, "PATH": os.pathsep.join(keep), "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
    script = str(UYEN_DIR / "install_hermes_profile.sh")
    first = subprocess.run([BASH, script], env=env, capture_output=True, text=True, timeout=120)
    assert first.returncode == 0, first.stderr
    dst = tmp_path / ".hermes" / "profiles" / "ted_for_uyen"
    installed = {p.name for p in (dst / "skills").iterdir()}
    assert {p.name for p in COMMON_SKILLS_DIR.iterdir()} <= installed
    assert {"ted-cheer", "ted-health-break", "ted-deep-work", "uyen-thcs-bridge", "uyen-evening-planner"} <= installed
    assert "ted-email-digest" not in installed and "ted-calendar-today" not in installed
    assert (dst / "skills" / "ted-deep-work" / "SKILL.md").read_text(encoding="utf-8") == \
        (UYEN_DIR / "skills" / "ted-deep-work" / "SKILL.md").read_text(encoding="utf-8")
    assert "__TED_MCP_SERVER_PATH__" not in (dst / "config.yaml").read_text(encoding="utf-8")
    assert "src/bridge/ted_mcp_server.py" in (dst / "config.yaml").read_text(encoding="utf-8")

    (dst / "knowledge" / "evening-settings.json").write_text('{"computer_start": "17:30"}', encoding="utf-8")
    second = subprocess.run([BASH, script], env=env, capture_output=True, text=True, timeout=120)
    assert second.returncode == 0, second.stderr
    assert "17:30" in (dst / "knowledge" / "evening-settings.json").read_text(encoding="utf-8")   # không ghi đè
    assert (dst / "config.yaml.new").exists()
