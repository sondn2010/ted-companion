"""install_hermes_profile.sh chạy 2 lần vào HOME tạm: giữ dữ liệu Hermes đã ghi, skill chung đủ 6 (coach), work không có."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from skill_sample_extraction_helper import COMMON_SKILLS_DIR, PROFILES_DIR, SHARED_SKILLS_DIR

BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="cần bash")


def _install(home: Path, profile: str) -> subprocess.CompletedProcess:
    # HERMES_SKIP_PROFILE_CREATE=1: KHÔNG gọi CLI hermes thật (nó bỏ qua $HOME)
    env = {**os.environ, "HOME": str(home), "HERMES_SKIP_PROFILE_CREATE": "1", "HERMES_ALLOW_ROOT": "1"}
    return subprocess.run([BASH, str(PROFILES_DIR / "install_hermes_profile.sh"), profile],
                          env=env, capture_output=True, text=True, timeout=120)


def test_caohoc_install_twice_is_idempotent_and_preserves_user_data(tmp_path):
    first = _install(tmp_path, "family_caohoc")
    assert first.returncode == 0, first.stderr
    dst = tmp_path / ".hermes" / "profiles" / "family_caohoc"
    shared = {p.name for p in SHARED_SKILLS_DIR.iterdir() if p.is_dir()}
    assert len(shared) == 6 and shared <= {p.name for p in (dst / "skills").iterdir()}

    (dst / "memories" / "USER.md").write_text("Hermes đã ghi", encoding="utf-8")
    (dst / "knowledge").mkdir(exist_ok=True)
    (dst / "knowledge" / "learning-plan.md").write_text("kế hoạch riêng", encoding="utf-8")
    key_line = next(ln for ln in (dst / ".env").read_text().splitlines() if ln.startswith("API_SERVER_KEY="))

    second = _install(tmp_path, "family_caohoc")
    assert second.returncode == 0, second.stderr
    assert (dst / "memories" / "USER.md").read_text(encoding="utf-8") == "Hermes đã ghi"
    assert (dst / "knowledge" / "learning-plan.md").read_text(encoding="utf-8") == "kế hoạch riêng"
    assert key_line in (dst / ".env").read_text().splitlines()   # key sinh 1 lần, không đổi
    assert (dst / "config.yaml.new").exists()                    # config cũ giữ nguyên, bản mới để cạnh bên


def test_work_profile_gets_no_shared_coach_skills(tmp_path):
    result = _install(tmp_path, "family_work")
    assert result.returncode == 0, result.stderr
    installed = {p.name for p in (tmp_path / ".hermes" / "profiles" / "family_work" / "skills").iterdir()}
    assert installed.isdisjoint({p.name for p in SHARED_SKILLS_DIR.iterdir()})
    assert "ted-briefing" in installed and "ted-health-break" in installed   # skill riêng của family_work
    assert {p.name for p in COMMON_SKILLS_DIR.iterdir() if p.is_dir()} <= installed   # _common vào mọi kind


def test_coach_profile_gets_common_untangle_skill_and_shared(tmp_path):
    result = _install(tmp_path, "family_thcs")
    assert result.returncode == 0, result.stderr
    installed = {p.name for p in (tmp_path / ".hermes" / "profiles" / "family_thcs" / "skills").iterdir()}
    assert "ted-idea-untangle" in installed
    assert {p.name for p in SHARED_SKILLS_DIR.iterdir()} <= installed


# ---- Profile riêng của Ted (hermes_profile_ted): tập cha của family_work ----
TED_DIR = PROFILES_DIR.parent / "hermes_profile_ted"
WORK_SKILLS_DIR = PROFILES_DIR / "family_work" / "skills"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


def _env_without_hermes_cli(home: Path) -> dict:
    """Env cô lập: HOME tạm + PATH bỏ thư mục chứa CLI hermes thật (installer Ted không có cờ bỏ qua)."""
    keep = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d and shutil.which("hermes", path=d) is None]
    return {**os.environ, "PATH": os.pathsep.join(keep), "HOME": str(home), "USERPROFILE": str(home)}


def _skill_names(root: Path) -> set:
    return {p.name for p in root.iterdir() if p.is_dir()}


def _assert_ted_superset(dst: Path):
    skills = dst / "skills"
    installed = _skill_names(skills)
    assert _skill_names(WORK_SKILLS_DIR) <= installed          # đủ skill của family_work (health-break, briefing, ...)
    assert "ted-health-break" in installed and "ted-eisenhower-classify" in installed
    assert _skill_names(COMMON_SKILLS_DIR) <= installed        # _common vẫn có
    assert installed.isdisjoint(_skill_names(SHARED_SKILLS_DIR))   # không lẫn skill coach
    # trùng tên: bản của Ted thắng (nội dung giống skills/ted-deep-work của Ted, khác bản family_work)
    own = (TED_DIR / "skills" / "ted-deep-work" / "SKILL.md").read_text(encoding="utf-8")
    work = (WORK_SKILLS_DIR / "ted-deep-work" / "SKILL.md").read_text(encoding="utf-8")
    assert own != work
    assert (skills / "ted-deep-work" / "SKILL.md").read_text(encoding="utf-8") == own


def test_ted_bash_install_is_superset_of_family_work_and_own_copy_wins(tmp_path):
    env = _env_without_hermes_cli(tmp_path)
    stale = tmp_path / ".hermes" / "profiles" / "ted" / "skills" / "ted-cheer" / "stale-file.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("cũ", encoding="utf-8")
    done = subprocess.run([BASH, str(TED_DIR / "install_hermes_profile.sh")], env=env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    _assert_ted_superset(tmp_path / ".hermes" / "profiles" / "ted")
    assert not stale.exists()   # file cũ bị dọn khi cài lại


@pytest.mark.skipif(POWERSHELL is None, reason="cần PowerShell")
def test_ted_powershell_install_is_superset_prunes_stale_and_handles_brackets(tmp_path):
    home = tmp_path / "home [x]"   # ký tự [ ] trong đường dẫn: phải dùng -LiteralPath
    home.mkdir()
    env = _env_without_hermes_cli(home)
    stale = home / ".hermes" / "profiles" / "ted" / "skills" / "ted-cheer" / "stale-file.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("cũ", encoding="utf-8")
    done = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(TED_DIR / "install_hermes_profile.ps1")], env=env,
                          capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stdout + done.stderr
    _assert_ted_superset(home / ".hermes" / "profiles" / "ted")
    assert not stale.exists()
