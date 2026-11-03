"""Đọc Character Pack (bộ nhân vật dựng trong docs/UI/characters/<pack>) đã cài vào assets/character_pack.

Pack = 1 thư mục có `characters.json` + ảnh PNG. Các pack hiện có ghi ảnh trạng thái theo nhiều kiểu khác nhau,
nên chuẩn hoá ở đây (theo thứ tự ưu tiên):
  1. `mood_images[state]`            vd "animations/linh_idle.png" hoặc "char_01_bao_chau_idle.png"
  2. `assets.animations[state]`
  3. quy ước `animations/{id}_{state}.png`, rồi `{id}_{state}.png`
Avatar (dùng khi thiếu ảnh trạng thái): `avatar_file` hoặc `assets.full_body.path`.

Module thuần Python (không Qt, không import config) → dùng chung cho app và scripts/install_character_pack.py.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ted")

PACK_MANIFEST_NAME = "characters.json"
# Trạng thái ảnh mà pet cần (khớp MOOD_SUFFIX_MAP của companion_widget)
STATE_IDS = ("idle", "focus", "cheer", "rest", "nudge")
# Mood của FocusEngine → trạng thái ảnh / câu thoại trong pack
MOOD_TO_STATE = {"IDLE": "idle", "FOCUS": "focus", "GENTLE_NUDGE": "nudge", "CHEER": "cheer", "REST": "rest"}


@dataclass
class PackCharacter:
    id: str
    display_name: str
    personality_key: str = ""
    voice_config: dict = field(default_factory=dict)
    catchphrases: list[str] = field(default_factory=list)
    expressions: dict[str, list[str]] = field(default_factory=dict)   # {state: [câu, ...]}
    state_images: dict[str, Path] = field(default_factory=dict)       # chỉ chứa ảnh tồn tại
    avatar: Optional[Path] = None
    title: str = ""
    role: str = ""
    gender: str = ""
    personality_desc: str = ""
    raw_tags: list[str] = field(default_factory=list)

    @property
    def missing_states(self) -> list[str]:
        return [s for s in STATE_IDS if s not in self.state_images]

    def image_for(self, state: str) -> Optional[Path]:
        """Ảnh cho trạng thái; thiếu → ảnh idle → avatar."""
        return self.state_images.get(state) or self.state_images.get("idle") or self.avatar


@dataclass
class CharacterPack:
    id: str
    title: str
    pack_dir: Path
    characters: dict[str, PackCharacter]
    default_character_id: str

    def missing_report(self) -> dict[str, list[str]]:
        """{character_id: [trạng thái thiếu ảnh]} — rỗng nghĩa là pack đầy đủ animation."""
        return {cid: c.missing_states for cid, c in self.characters.items() if c.missing_states}

    def imageless_characters(self) -> list[str]:
        """Nhân vật không có cả ảnh idle lẫn avatar → pet sẽ vô hình, không được phép cài."""
        return [cid for cid, c in self.characters.items() if c.image_for("idle") is None]


def _existing(pack_dir: Path, rel) -> Optional[Path]:
    if not isinstance(rel, str) or not rel.strip():
        return None
    path = pack_dir / rel.strip()
    return path if path.is_file() else None


def _resolve_state_images(pack_dir: Path, raw: dict, cid: str) -> dict[str, Path]:
    mood_images = raw.get("mood_images") if isinstance(raw.get("mood_images"), dict) else {}
    assets = raw.get("assets") if isinstance(raw.get("assets"), dict) else {}
    animations = assets.get("animations") if isinstance(assets.get("animations"), dict) else {}
    # Tên gốc file: id nhân vật, và tên file avatar (vd id "mai_chi_vest" nhưng ảnh "char_01_mai_chi_vest_idle.png")
    stems = [cid]
    if isinstance(raw.get("avatar_file"), str) and Path(raw["avatar_file"]).stem not in stems:
        stems.append(Path(raw["avatar_file"]).stem)
    images = {}
    for state in STATE_IDS:
        conventions = [p for stem in stems for p in (f"animations/{stem}_{state}.png", f"{stem}_{state}.png")]
        for rel in (mood_images.get(state), animations.get(state), *conventions):
            path = _existing(pack_dir, rel)
            if path is not None:
                images[state] = path
                break
    return images


def _resolve_avatar(pack_dir: Path, raw: dict) -> Optional[Path]:
    assets = raw.get("assets") if isinstance(raw.get("assets"), dict) else {}
    full_body = assets.get("full_body") if isinstance(assets.get("full_body"), dict) else {}
    return _existing(pack_dir, raw.get("avatar_file")) or _existing(pack_dir, full_body.get("path"))


def _string_list(value) -> list[str]:
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


def _parse_character(pack_dir: Path, raw: dict) -> Optional[PackCharacter]:
    cid = str(raw.get("id") or "").strip()
    if not cid:
        return None
    expressions = raw.get("expressions") if isinstance(raw.get("expressions"), dict) else {}
    p_desc = str(raw.get("personality") or raw.get("personality_details") or raw.get("description") or "").strip()
    return PackCharacter(
        id=cid,
        display_name=str(raw.get("display_name") or raw.get("name") or cid).strip(),
        personality_key=str(raw.get("personality_key") or "").strip(),
        voice_config=raw.get("voice_config") if isinstance(raw.get("voice_config"), dict) else {},
        catchphrases=_string_list(raw.get("catchphrases")),
        expressions={str(k).lower(): _string_list(v) for k, v in expressions.items() if _string_list(v)},
        state_images=_resolve_state_images(pack_dir, raw, cid),
        avatar=_resolve_avatar(pack_dir, raw),
        title=str(raw.get("title") or "").strip(),
        role=str(raw.get("role") or "").strip(),
        gender=str(raw.get("gender") or "").strip(),
        personality_desc=p_desc,
        raw_tags=_string_list(raw.get("tags")),
    )


def load_character_pack(pack_dir: Path) -> Optional[CharacterPack]:
    """Nạp pack từ thư mục; không có / hỏng / không có nhân vật nào → None (app dùng 6 con vật mặc định)."""
    manifest = Path(pack_dir) / PACK_MANIFEST_NAME
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("Không đọc được character pack %s: %s", manifest, exc)
        return None
    if not isinstance(data, dict):
        return None
    characters = {}
    for raw in data.get("characters") or []:
        if isinstance(raw, dict):
            character = _parse_character(Path(pack_dir), raw)
            if character is not None and character.id not in characters:
                characters[character.id] = character
    if not characters:
        logger.error("Character pack %s không có nhân vật hợp lệ", manifest)
        return None
    default_id = str(data.get("default_character_id") or "")
    return CharacterPack(
        id=str(data.get("pack_id") or data.get("id") or Path(pack_dir).name),
        title=str(data.get("title") or ""),
        pack_dir=Path(pack_dir),
        characters=characters,
        default_character_id=default_id if default_id in characters else next(iter(characters)),
    )
