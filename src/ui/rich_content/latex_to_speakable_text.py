"""Đổi câu trả lời giàu định dạng thành văn bản để TTS đọc: bỏ hình vẽ/mã, đọc công thức thành lời.

Ví dụ (tiếng Việt): `$x^2 + \\frac{1}{2}$` → "x bình phương cộng 1 phần 2".
"""

import re

from src.ui.rich_content.latex_unicode_fallback import latex_to_unicode
from src.ui.rich_content.rich_reply_segment_patterns import (
    DISPLAY_MATH_RE,
    FENCE_RE,
    INLINE_MATH_RE,
    RAW_SVG_RE,
    TABLE_SEPARATOR_RE,
)

_VI_CHARS = re.compile(r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]", re.I)

WORDS = {
    "vi": {"²": " bình phương", "³": " lập phương", "√": " căn của ", "∛": " căn bậc ba của ", "/": " phần ",
           "=": " bằng ", "+": " cộng ", "−": " trừ ", "×": " nhân ", "·": " nhân ", "÷": " chia ",
           "≤": " nhỏ hơn hoặc bằng ", "≥": " lớn hơn hoặc bằng ", "<": " nhỏ hơn ", ">": " lớn hơn ",
           "≠": " khác ", "≈": " xấp xỉ ", "π": " pi ", "∞": " vô cùng ", "⇒": " suy ra ", "∈": " thuộc ",
           "⊥": " vuông góc với ", "∥": " song song với ", "∠": " góc ", "△": " tam giác ", "°": " độ ",
           "±": " cộng trừ ", "%": " phần trăm "},
    "en": {"²": " squared", "³": " cubed", "√": " square root of ", "∛": " cube root of ", "/": " over ",
           "=": " equals ", "+": " plus ", "−": " minus ", "×": " times ", "·": " times ", "÷": " divided by ",
           "≤": " less than or equal to ", "≥": " greater than or equal to ", "<": " less than ",
           ">": " greater than ", "≠": " not equal to ", "≈": " approximately ", "π": " pi ", "∞": " infinity ",
           "⇒": " implies ", "∈": " in ", "⊥": " perpendicular to ", "∥": " parallel to ", "∠": " angle ",
           "△": " triangle ", "°": " degrees ", "±": " plus or minus ", "%": " percent "},
}


def speak_math(latex: str, lang: str = "vi") -> str:
    text = latex_to_unicode(latex).replace("-", "−")
    text = re.sub(r"[()]", " ", text)
    for symbol, word in WORDS[lang].items():
        text = text.replace(symbol, word)
    return " ".join(text.split())


def speakable_text_from_rich_reply(text: str) -> str:
    if not text:
        return ""
    lang = "vi" if _VI_CHARS.search(text) else "en"
    figure = " (hình vẽ) " if lang == "vi" else " (figure) "
    out = FENCE_RE.sub(lambda m: figure if m.group(1).lower() == "svg" else " ", text)
    out = RAW_SVG_RE.sub(figure, out)
    out = DISPLAY_MATH_RE.sub(lambda m: f" {speak_math(m.group(1) or m.group(2), lang)}. ", out)
    out = INLINE_MATH_RE.sub(lambda m: f" {speak_math(m.group(1) or m.group(2), lang)} ", out)
    lines = []
    for line in out.splitlines():
        if TABLE_SEPARATOR_RE.match(line):
            continue
        if line.strip().startswith("|"):   # hàng bảng → các ô ngăn bằng dấu phẩy
            line = ", ".join(c.strip() for c in line.strip().strip("|").split("|") if c.strip())
        lines.append(line)
    return "\n".join(lines)
