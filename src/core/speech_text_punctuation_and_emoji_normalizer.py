"""Chuẩn hoá văn bản trước khi đọc TTS: bỏ emoji/icon, giữ ngắt nghỉ theo dòng, chuẩn dấu câu.

TTS (Piper / server) nhấn nhá dựa vào dấu câu: dấu phẩy = nghỉ ngắn, dấu chấm/!/? = nghỉ dài.
Vì vậy mỗi dòng (gạch đầu dòng, câu xuống dòng) phải kết thúc bằng dấu câu, và mọi icon phải bị
loại bỏ hoàn toàn để giọng đọc không phát âm tên ký tự hay ngập ngừng.
"""

import re
import unicodedata

# Ký tự symbol (So) vẫn nên giữ vì đọc được / mang nghĩa
_KEEP_SYMBOLS = {"°", "%"}
# Ký tự vô hình đi kèm emoji: variation selector, zero-width joiner, keycap, tag sequence
_INVISIBLE_RE = re.compile("[‍⃣︎️\U000e0020-\U000e007f]")
# Đầu dòng dạng gạch đầu dòng / heading / trích dẫn markdown
_BULLET_RE = re.compile(r"^\s*(?:[-*+•·▪▫◦‣⁃>]+|#{1,6})\s*")
# Gạch ngang dài, mũi tên giữa câu → nghỉ ngắn
_DASH_ARROW_RE = re.compile(r"\s*(?:[–—―]|\s-\s|->|=>|[→⇒➜➔⟶])\s*")
_ELLIPSIS_RE = re.compile(r"…|\.{2,}")
_PAREN_RE = re.compile(r"\s*[\(\[\{]\s*([^)\]\}]*?)\s*[\)\]\}]")
_QUOTES_RE = re.compile(r"[\"“”„«»‘’`|]")
# Dấu câu lặp hoặc chồng nhau: "!!!", "?!", ",,", ", ."
_REPEAT_PUNCT_RE = re.compile(r"([,.;:!?])(?:\s*[,.;:!?])+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")
# Thiếu khoảng trắng sau dấu câu: trước chữ cái, hoặc chữ cái + dấu + số ("giờ,1") — không đụng 10:30, 3.5, 1,000
_MISSING_SPACE_RE = re.compile(r"([,;:!?]|(?<!\d)\.)(?=[^\W\d_])|(?<=[^\W\d_])([,;:!?.])(?=\d)")
_SENTENCE_END = (".", "!", "?", ":", ";", ",")


def _is_icon(ch: str) -> bool:
    """Emoji, icon, ký hiệu hình vẽ (Unicode So/Co/Cs) → không đọc."""
    if ch in _KEEP_SYMBOLS:
        return False
    cat = unicodedata.category(ch)
    if cat in ("So", "Co", "Cs"):
        return True
    return cat == "Sk" and ord(ch) >= 0x1F3FB  # màu da emoji (skin tone modifier)


def strip_icons(text: str) -> str:
    text = _INVISIBLE_RE.sub("", text)
    return "".join(" " if _is_icon(ch) else ch for ch in text)


def _normalize_line(line: str) -> str:
    line = _BULLET_RE.sub("", line)
    line = _ELLIPSIS_RE.sub(". ", line)
    line = _DASH_ARROW_RE.sub(", ", line)
    line = _PAREN_RE.sub(lambda m: f", {m.group(1)}, " if m.group(1) else " ", line)
    line = _QUOTES_RE.sub("", line)
    line = " ".join(line.split()).strip(" ,;")
    return line


def _tidy_punctuation(text: str) -> str:
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    # Giữ dấu "mạnh" nhất trong cụm: ? > ! > . > ; > : > ,
    def strongest(m: re.Match) -> str:
        group = re.sub(r"\s", "", m.group(0))
        for p in "?!.;:,":
            if p in group:
                return p
        return m.group(1)

    text = _REPEAT_PUNCT_RE.sub(strongest, text)
    text = _MISSING_SPACE_RE.sub(lambda m: (m.group(1) or m.group(2)) + " ", text)
    text = re.sub(r"^[\s,.;:!?]+", "", text)
    return " ".join(text.split()).strip()


def normalize_text_for_speech(text: str) -> str:
    """Bỏ icon, mỗi dòng thành một câu có dấu kết thúc, chuẩn dấu câu để TTS ngắt nghỉ tự nhiên."""
    if not text:
        return ""
    sentences = []
    for raw in strip_icons(text).splitlines():
        line = _normalize_line(raw)
        if not line:
            continue
        if not line.endswith(_SENTENCE_END):
            line += "."
        elif line.endswith(","):  # dòng kết thúc dở dang bằng dấu phẩy → nghỉ như hết câu
            line = line[:-1] + "."
        sentences.append(line)
    return _tidy_punctuation(" ".join(sentences))
