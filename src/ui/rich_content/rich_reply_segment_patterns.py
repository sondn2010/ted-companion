"""Regex nhận diện các đoạn đặc biệt trong câu trả lời của Ted (dùng chung cho hiển thị và đọc TTS).

Quy ước định dạng (đã hướng dẫn trong prompt / skill của Hermes):
- Công thức: `$...$` (trong dòng), `$$...$$` hoặc `\\[...\\]` (riêng dòng), `\\(...\\)`.
- Hình vẽ: khối ```svg ... ``` hoặc thẻ <svg>...</svg>.
- Bảng / biểu mẫu: bảng markdown `| a | b |` + dòng `|---|---|`.
"""

import re

FENCE_RE = re.compile(r"```[ \t]*([\w+-]*)[ \t]*\n(.*?)```", re.S)
RAW_SVG_RE = re.compile(r"<svg\b.*?</svg>", re.S | re.I)
DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]", re.S)
# $...$: không ăn tiền tệ kiểu "50$" / "$5 và $10" (không sát khoảng trắng, không dính chữ/số bên ngoài)
INLINE_MATH_RE = re.compile(r"(?<![\\$\w])\$(?![\s$])([^$\n]+?)(?<![\s\\])\$(?![\w$])|\\\((.+?)\\\)")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
MARKDOWN_HINT_RE = re.compile(r"^\s{0,3}(#{1,4}\s|[-*+]\s|\d+[.)]\s|>\s)|\*\*[^*]+\*\*|`[^`]+`", re.M)


def has_rich_markup(text: str) -> bool:
    """Có cần dựng HTML giàu định dạng không (giữ nguyên hành vi chữ thuần cho câu trả lời bình thường)."""
    if not text:
        return False
    return bool(
        FENCE_RE.search(text) or RAW_SVG_RE.search(text) or DISPLAY_MATH_RE.search(text)
        or INLINE_MATH_RE.search(text) or any(TABLE_SEPARATOR_RE.match(ln) for ln in text.splitlines())
        or MARKDOWN_HINT_RE.search(text)
    )
