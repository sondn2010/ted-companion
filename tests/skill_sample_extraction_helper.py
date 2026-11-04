"""Rút các khối <json>...</json> mẫu từ SKILL.md và đường dẫn repo dùng chung cho test hợp đồng."""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if not (REPO_ROOT / "hermes_profiles").exists() and (REPO_ROOT.parent / "hermes_profiles").exists():
    REPO_ROOT = REPO_ROOT.parent
PROFILES_DIR = REPO_ROOT / "hermes_profiles"
SHARED_SKILLS_DIR = PROFILES_DIR / "_shared" / "skills"
JSON_BLOCK_RE = re.compile(r"<json>(.*?)</json>", re.S)

# Chỉ chỗ này được phép sửa mẫu có placeholder "..." (ghi rõ lý do); mặc định mẫu phải parse nguyên văn.
SAMPLE_FIXUPS: dict[str, str] = {}   # hiện không cần: mọi mẫu response đều hợp lệ nguyên văn


WORK_SKILLS_DIR = PROFILES_DIR / "family_work" / "skills"
COMMON_SKILLS_DIR = PROFILES_DIR / "_common" / "skills"   # skill cài cho MỌI profile (kind nào cũng có)


def skill_text(skill: str) -> str:
    """Tìm SKILL.md ở _shared, rồi _common (mọi profile), rồi family_work (skill riêng của module Work)."""
    for base in (SHARED_SKILLS_DIR, COMMON_SKILLS_DIR, WORK_SKILLS_DIR):
        path = base / skill / "SKILL.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"không có SKILL.md cho {skill}")


def json_samples(skill: str) -> list[dict]:
    """Mọi khối <json> parse được thành dict của skill (khối không phải JSON như placeholder bị bỏ qua)."""
    samples = []
    for raw in JSON_BLOCK_RE.findall(skill_text(skill)):
        raw = SAMPLE_FIXUPS.get(raw.strip(), raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            samples.append(data)
    return samples


def sample_with_key(skill: str, key: str) -> dict:
    for sample in json_samples(skill):
        if key in sample:
            return sample
    raise AssertionError(f"{skill}: không có mẫu <json> chứa khoá '{key}'")
