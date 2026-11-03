"""Tầng 4 — Lexicon & Phonetic Mapper: thay tên riêng / từ tiếng Anh bằng cách đọc kiểu Việt ("Harry Potter" → "he ri pót tơ")
và hạ chữ IN HOA dài về dạng thường ("SLYTHERIN" → "Slytherin") để G2P không đánh vần từng chữ cái.

Từ điển = các file lexicon_*.json đi kèm app + từ điển người dùng ~/.ted/custom_lexicon.json (ưu tiên cao nhất).
Khớp nguyên từ, không phân biệt hoa thường, cụm dài khớp trước ("Harry Potter" thắng "Harry").
Nhập / xuất: JSON phẳng {"từ gốc": "cách đọc"}.
"""

import json
import logging
import re
from pathlib import Path

from src.config import settings
from src.core.vieneu_story_preprocessor.core.config_loader import load_config, load_json

logger = logging.getLogger("ted")

BUNDLED_LEXICONS = ("lexicon_common_vi.json", "lexicon_hogwarts.json", "lexicon_middle_earth.json")
CUSTOM_LEXICON_NAME = "custom_lexicon.json"
_WORD_RE = re.compile(r"[^\W\d_]+")
_CAPS_MIN_LEN = 5   # IN HOA ngắn hơn (API, PDF) là từ viết tắt: để từ điển / model tự đánh vần

_compiled: dict = {"parts": None, "regex": None, "mapping": {}, "originals": {}}


def custom_lexicon_path() -> Path:
    return Path(settings.data_dir) / CUSTOM_LEXICON_NAME


def validate_lexicon(data) -> dict[str, str]:
    if not isinstance(data, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip() for k, v in data.items()):
        raise ValueError('Từ điển phải là JSON dạng {"từ gốc": "cách đọc"} với chuỗi không rỗng.')
    return {" ".join(k.split()): " ".join(v.split()) for k, v in data.items()}


def _load_custom_raw():
    try:
        return load_json(custom_lexicon_path(), {})
    except ValueError as exc:   # JSON hỏng: đọc tiếp bằng từ điển đi kèm thay vì làm hỏng giọng đọc
        logger.warning("Bỏ qua từ điển phát âm của người dùng: %s", exc)
        return {}


def load_custom_lexicon() -> dict[str, str]:
    try:
        return validate_lexicon(_load_custom_raw())
    except ValueError as exc:
        logger.warning("Bỏ qua từ điển phát âm của người dùng: %s", exc)
        return {}


def merged_lexicon() -> dict[str, str]:
    merged: dict[str, str] = {}
    for name in BUNDLED_LEXICONS:
        merged.update(load_config(name) or {})
    merged.update(load_custom_lexicon())
    return merged


def import_lexicon(src: Path) -> int:
    """Gộp file JSON vào từ điển người dùng (mục trùng thì file nhập thắng). Trả số mục đã nhập."""
    entries = validate_lexicon(json.loads(Path(src).read_text(encoding="utf-8")))
    merged = {**load_custom_lexicon(), **entries}
    path = custom_lexicon_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(entries)


def export_lexicon(dest: Path) -> int:
    """Xuất toàn bộ từ điển đang dùng (đi kèm + người dùng) → sửa rồi nhập lại. Trả số mục."""
    merged = merged_lexicon()
    Path(dest).write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(merged)


def _matcher() -> tuple[re.Pattern | None, dict[str, str]]:
    parts = [load_config(name) for name in BUNDLED_LEXICONS] + [_load_custom_raw()]
    cached = _compiled["parts"]
    if cached is None or len(cached) != len(parts) or any(a is not b for a, b in zip(cached, parts)):
        merged = merged_lexicon()
        mapping = {k.casefold(): v for k, v in merged.items()}
        keys = sorted(mapping, key=len, reverse=True)
        regex = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, keys)) + r")(?!\w)", re.I) if keys else None
        _compiled.update(parts=parts, regex=regex, mapping=mapping, originals={k.casefold(): k for k in merged})
    return _compiled["regex"], _compiled["mapping"]


def known_name_words() -> set[str]:
    """Các từ (casefold) thuộc tên riêng trong từ điển — bộ tách hội thoại dùng để nhận ra câu trần thuật."""
    return {w.casefold() for key in merged_lexicon() if key[:1].isupper() for w in key.split()}


def normalize_caps(text: str, min_len: int = _CAPS_MIN_LEN) -> str:
    return _WORD_RE.sub(lambda m: m.group(0).capitalize()
                        if len(m.group(0)) >= min_len and m.group(0).isupper() else m.group(0), text)


def _replace(m: re.Match, mapping: dict[str, str], originals: dict[str, str]) -> str:
    found = m.group(0)
    key = found.casefold()
    if originals[key].isupper() and found != originals[key]:
        return found   # từ viết tắt (AI, OK) chỉ khớp đúng chữ hoa: "ai", "ok" tiếng Việt giữ nguyên
    reading = mapping[key]
    if found[:1].isupper() and not found.isupper():   # tên riêng / đầu câu vẫn viết hoa
        return reading[:1].upper() + reading[1:]
    return reading


def map_pronunciation(text: str) -> str:
    text = normalize_caps(text)
    regex, mapping = _matcher()
    originals = _compiled["originals"]
    return regex.sub(lambda m: _replace(m, mapping, originals), text) if regex else text
