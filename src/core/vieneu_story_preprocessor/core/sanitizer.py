"""Tầng 1 — Text & DOM Sanitizer: bỏ metadata đầu chương, khôi phục Drop Cap, chuẩn hoá Unicode / ngoặc kép / gạch ngang.

Giữ nguyên cấu trúc đoạn (mỗi dòng một đoạn) để tầng ngắt nghỉ biết chỗ xuống đoạn (P-13), đổi cảnh (P-14), gạch đầu dòng.
"""

import re
import unicodedata
from dataclasses import dataclass

from src.core.speech_text_punctuation_and_emoji_normalizer import strip_icons
from src.core.vieneu_story_preprocessor.core.config_loader import load_config


@dataclass
class Paragraph:
    text: str
    kind: str = "text"   # text | list_item | scene_break


_SCENE_BREAK_RE = re.compile(r"^\s*(?:[*_\-=~•·⁂]\s*){3,}$")
# "1.234 từ · 5 phút đọc", "12 min read", dòng CSV dính liền
_METADATA_RE = re.compile(r"^(?:[\d.,]+\s*(?:từ|chữ|words?)|\d+\s*(?:phút|min(?:ute)?s?)\s*(?:đọc|read))\b", re.I)
_CSV_RE = re.compile(r"^[^\s,]+(?:,[^\s,]*){3,}$")
_BULLET_RE = re.compile(r"^(?:([-*+•·▪▫◦‣⁃]+)|>+|#{1,6})\s*")
_NUMBERED_RE = re.compile(r"^(\d{1,2})[.)]\s+")
_MARKDOWN_RE = re.compile(r"[*_`~]")
_DOUBLE_QUOTES_RE = re.compile(r"[“”„«»]")
_ELLIPSIS_RE = re.compile(r"…|\.{2,}")
_ARROW_RE = re.compile(r"\s*(?:->|=>|[→⇒➜➔⟶])\s*")
_DASH_RE = re.compile(r"\s*(?:—|―|–|--)\s*|\s+-\s+")
_PAREN_RE = re.compile(r"\s*[\(\[\{]\s*([^)\]\}]*?)\s*[\)\]\}]")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")
_HAS_WORD_RE = re.compile(r"[^\W_]")
_TERMINAL = (".", "!", "?", ":", ";")


def _clean_inline(line: str) -> str:
    line = _MARKDOWN_RE.sub("", line)
    line = _DOUBLE_QUOTES_RE.sub('"', line).replace("‘", "'").replace("’", "'")
    line = _ELLIPSIS_RE.sub("...", line)
    line = _ARROW_RE.sub(", ", line)
    line = _DASH_RE.sub(" — ", line)
    line = _PAREN_RE.sub(lambda m: f", {m.group(1)}, " if m.group(1) else " ", line)
    line = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", " ".join(line.split()))
    line = re.sub(r",(?:\s*,)+", ",", line)
    line = re.sub(r",\s*([.!?;:])", r"\1", line)
    return line.strip(" ,;").lstrip("— ").strip()


def _ensure_terminal(line: str) -> str:
    core = line.rstrip('"')
    if core.endswith(_TERMINAL):
        return line
    if core.endswith(","):
        return core[:-1] + "." + line[len(core):]
    return line + "."


def _merge_drop_cap(lines: list[str]) -> list[str]:
    """Drop Cap tách rời trên DOM: dòng chỉ có 1 chữ hoa, dòng có chữ kế tiếp bắt đầu bằng chữ thường → ghép lại."""
    out: list[str] = []
    pending = ""
    for line in lines:
        stripped = line.strip()
        if pending:
            if not stripped:
                continue
            if stripped[0].islower():
                out.append(pending + stripped)
                pending = ""
                continue
            out.append(pending)
            pending = ""
        if len(stripped) == 1 and stripped.isupper():
            pending = stripped
        else:
            out.append(line)
    if pending:
        out.append(pending)
    return out


def _recover_opening(text: str) -> str:
    """Đầu chương mất chữ cái đầu ("ặt nước" → "Mặt nước") theo từ điển cụm mở đầu."""
    if not text[:1].islower():
        return text
    for broken, fixed in (load_config("drop_cap_openings.json") or {}).items():
        if text.startswith(broken) and not text[len(broken):len(broken) + 1].isalnum():
            return fixed + text[len(broken):]
    return text


def sanitize(text: str) -> list[Paragraph]:
    lines = _merge_drop_cap(strip_icons(unicodedata.normalize("NFC", text or "")).splitlines())
    paragraphs: list[Paragraph] = []
    for raw in lines:
        if _SCENE_BREAK_RE.match(raw):
            if paragraphs and paragraphs[-1].kind != "scene_break":
                paragraphs.append(Paragraph("", "scene_break"))
            continue
        line = raw.strip()
        if not line or _METADATA_RE.match(line) or _CSV_RE.match(line):
            continue
        kind = "text"
        numbered = _NUMBERED_RE.match(line)
        bullet = _BULLET_RE.match(line)
        if numbered:
            line, kind = f"{numbered.group(1)}, {line[numbered.end():]}", "list_item"
        elif bullet:
            line, kind = line[bullet.end():], "list_item" if bullet.group(1) else "text"
        line = _clean_inline(line)
        if _HAS_WORD_RE.search(line):   # dòng chỉ còn "..." / dấu câu: không có gì để đọc
            paragraphs.append(Paragraph(_ensure_terminal(line), kind))
    while paragraphs and paragraphs[-1].kind == "scene_break":
        paragraphs.pop()
    first = next((p for p in paragraphs if p.kind != "scene_break"), None)
    if first is not None:
        first.text = _recover_opening(first.text)
    return paragraphs
