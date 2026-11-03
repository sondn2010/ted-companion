"""Dữ liệu + ảnh cho trang Bộ sưu tập nhân vật: danh sách nhân vật (có sẵn + bundle) và nạp ảnh 5 trạng thái.

Ảnh PNG (pack / bundle) hoặc SVG (6 con vật gốc) → QPixmap vuông đã thu nhỏ, cache theo (đường dẫn, cỡ, khoá).
Nhân vật khoá được vẽ phủ xám (SourceAtop) để còn thấy hình dáng nhưng "tối đi".
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from src.config import (CHARACTER_SKINS, PACK_CHARACTERS, UNLOCKABLE_PACK_TITLES, UNLOCKABLE_SKINS, get_resource_path)
from src.core.character_pack_loader import STATE_IDS
from src.core.character_persona_profiles import DEFAULT_PERSONAS, get_personality
from src.core.i18n import get_character_skins, i18n
from src.core.unlockable_skin_registry_model import SkinCondition

BUILTIN_GROUP_ID = ""   # nhóm nhân vật có sẵn (6 con vật hoặc pack --pack), luôn đứng đầu

BUILTIN_ANIMAL_TAGS: dict[str, tuple[str, ...]] = {
    "cat": ("Có sẵn", "Động vật", "Mèo", "Vui vẻ"),
    "shiba": ("Có sẵn", "Động vật", "Cún", "Năng động"),
    "bunny": ("Có sẵn", "Động vật", "Thỏ", "Dễ thương"),
    "penguin": ("Có sẵn", "Động vật", "Cánh cụt", "Hài hước"),
    "owl": ("Có sẵn", "Động vật", "Cú", "Điềm tĩnh"),
    "panda": ("Có sẵn", "Động vật", "Gấu trúc", "Dễ thương"),
}

PACK_THEME_TAGS: dict[str, tuple[str, ...]] = {
    "01_chibi_adult_mature": ("Công sở", "Trưởng thành", "Áo vest"),
    "03_chibi_spicy_waifu": ("Waifu", "Quyến rũ"),
    "07_chibi_cute_snakes": ("Sinh vật", "Bé rắn"),
    "22_chibi_vietnamese_students": ("Học sinh", "Áo dài", "Việt Nam"),
    "25_chibi_vietnam_students_actions": ("Học sinh", "Việt Nam", "Hoạt cảnh"),
    "vietnam-chibi-pack": ("Việt Nam", "Áo dài", "Văn hóa"),
}

PERSONALITY_TAG_NAMES: dict[str, str] = {
    "cheerful": "Vui vẻ",
    "calm_wise": "Điềm tĩnh",
    "energetic": "Năng động",
    "sweet": "Dễ thương",
    "funny": "Hài hước",
    "disciplined": "Kỷ luật",
    "gentle": "Dịu dàng",
    "confident": "Tự tin",
    "analytical": "Sắc sảo",
}


@dataclass(frozen=True)
class GalleryEntry:
    key: str
    group_id: str                       # BUILTIN_GROUP_ID hoặc tên pack bundle
    group_title: str                    # "" cho nhóm có sẵn (UI dùng tr("gallery_group_builtin"))
    name_vi: str
    name_en: str
    condition: Optional[SkinCondition]  # None = nhân vật có sẵn (luôn mở)
    personality_key: str = "cheerful"
    personality_title: str = ""
    personality_desc: str = ""
    title: str = ""
    tags: tuple[str, ...] = ()
    quote: str = ""

    def name(self) -> str:
        return self.name_vi if i18n.current_language == "vi" else self.name_en

    def personality_short(self) -> str:
        """Tên ngắn cho thẻ (vd '😄 Vui vẻ' thay vì '😄 Vui vẻ, lạc quan')."""
        if not self.personality_title:
            return ""
        parts = self.personality_title.split(",")
        return parts[0].strip()


def build_gallery_entries() -> list[GalleryEntry]:
    """Nhân vật có sẵn trước (đúng thứ tự menu cũ), rồi từng pack bundle theo thứ tự registry."""
    entries = []
    vi_names, en_names = get_character_skins("vi"), get_character_skins("en")
    for key in CHARACTER_SKINS:
        if "/" in key:
            continue
        persona = DEFAULT_PERSONAS.get(key)
        p_key = persona.personality if persona else "cheerful"
        p_profile = get_personality(p_key)
        tags = BUILTIN_ANIMAL_TAGS.get(key, ("Có sẵn", "Động vật"))
        quote = p_profile.catchphrases[0].format(name=persona.name if persona else "Ted") if p_profile.catchphrases else ""
        entries.append(GalleryEntry(
            key=key,
            group_id=BUILTIN_GROUP_ID,
            group_title="",
            name_vi=vi_names.get(key) or CHARACTER_SKINS[key],
            name_en=en_names.get(key) or CHARACTER_SKINS[key],
            condition=None,
            personality_key=p_key,
            personality_title=p_profile.title,
            personality_desc=p_profile.description,
            title="",
            tags=tags,
            quote=quote,
        ))
    for skin in UNLOCKABLE_SKINS:
        title = UNLOCKABLE_PACK_TITLES.get(skin.pack) or skin.pack
        char = PACK_CHARACTERS.get(skin.key)
        p_key = char.personality_key if char and char.personality_key else "cheerful"
        p_profile = get_personality(p_key)
        p_desc = char.personality_desc if char and char.personality_desc else p_profile.description
        char_title = char.title if char and char.title else (char.role if char and char.role else "")
        quote = ""
        if char and char.catchphrases:
            quote = char.catchphrases[0]
        elif p_profile.catchphrases:
            quote = p_profile.catchphrases[0].format(name=char.display_name if char else skin.name_vi)
        tag_list: list[str] = list(PACK_THEME_TAGS.get(skin.pack, (skin.pack,)))
        ptag = PERSONALITY_TAG_NAMES.get(p_key)
        if ptag and ptag not in tag_list:
            tag_list.append(ptag)
        if char:
            if char.gender == "female" and "Nữ" not in tag_list:
                tag_list.append("Nữ")
            elif char.gender == "male" and "Nam" not in tag_list:
                tag_list.append("Nam")
            for t in getattr(char, "raw_tags", []):
                if t and t not in tag_list:
                    tag_list.append(t)
        entries.append(GalleryEntry(
            key=skin.key,
            group_id=skin.pack,
            group_title=title,
            name_vi=skin.name_vi,
            name_en=skin.name_en,
            condition=skin.condition,
            personality_key=p_key,
            personality_title=p_profile.title,
            personality_desc=p_desc,
            title=char_title,
            tags=tuple(tag_list),
            quote=quote,
        ))
    return entries


def _builtin_animal_image(key: str, state: str) -> Optional[Path]:
    """6 con vật gốc: ưu tiên PNG độ nét cao, sau đó SVG (cùng thứ tự với companion_widget)."""
    for rel in (f"assets/animations_png_preview/{key}_{state}.png", f"../docs/UI/animations_png_preview/{key}_{state}.png",
                f"assets/animations/{key}_{state}.png", f"assets/animations/{key}_{state}.svg"):
        path = get_resource_path(rel)
        if path.exists():
            return path
    return None


def state_image_path(key: str, state: str) -> Optional[Path]:
    character = PACK_CHARACTERS.get(key)
    return character.image_for(state) if character is not None else _builtin_animal_image(key, state)


_cache: dict[tuple, QPixmap] = {}


def _render(path: Path, px: int) -> QPixmap:
    if path.suffix.lower() == ".svg":
        pixmap = QPixmap(px, px)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(str(path)).render(painter, QRectF(0, 0, px, px))
        painter.end()
        return pixmap
    return QPixmap(str(path)).scaled(px, px, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


def _dim(pixmap: QPixmap) -> QPixmap:
    out = QPixmap(pixmap)
    painter = QPainter(out)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
    painter.fillRect(out.rect(), QColor(40, 42, 48, 205))
    painter.end()
    return out


def gallery_pixmap(key: str, state: str, px: int, locked: bool = False) -> Optional[QPixmap]:
    """Ảnh trạng thái đã thu nhỏ về `px` (cạnh dài); không có ảnh → None."""
    path = state_image_path(key, state)
    if path is None:
        return None
    cache_key = (str(path), px, locked)
    pixmap = _cache.get(cache_key)
    if pixmap is None or pixmap.isNull():
        base = _render(path, px)
        pixmap = _dim(base) if locked and not base.isNull() else base
        _cache[cache_key] = pixmap
    return pixmap


__all__ = ["GalleryEntry", "BUILTIN_GROUP_ID", "STATE_IDS", "build_gallery_entries", "gallery_pixmap", "state_image_path"]
