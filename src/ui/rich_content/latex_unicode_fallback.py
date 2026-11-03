"""Chuyển LaTeX đơn giản sang chữ Unicode dễ đọc (x², √(x), a/b, ≤, π…).

Dùng khi: (1) không vẽ được ảnh công thức (thiếu matplotlib / cú pháp mathtext không hỗ trợ),
(2) làm nền cho bản đọc thành lời của TTS. Không cố hiểu hết LaTeX — mục tiêu là học sinh vẫn đọc hiểu được.
"""

import re

SYMBOLS = {
    r"\times": "×", r"\div": "÷", r"\cdot": "·", r"\pm": "±", r"\mp": "∓",
    r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥", r"\neq": "≠", r"\ne": "≠",
    r"\approx": "≈", r"\equiv": "≡", r"\sim": "∼", r"\propto": "∝", r"\infty": "∞",
    r"\Rightarrow": "⇒", r"\Leftarrow": "⇐", r"\Leftrightarrow": "⇔", r"\rightarrow": "→", r"\to": "→",
    r"\leftarrow": "←", r"\implies": "⇒", r"\iff": "⇔",
    r"\in": "∈", r"\notin": "∉", r"\subset": "⊂", r"\subseteq": "⊆", r"\cup": "∪", r"\cap": "∩",
    r"\emptyset": "∅", r"\varnothing": "∅", r"\forall": "∀", r"\exists": "∃",
    r"\perp": "⊥", r"\parallel": "∥", r"\angle": "∠", r"\widehat": "∠", r"\triangle": "△", r"\Delta": "Δ",
    r"\circ": "°", r"\degree": "°", r"\%": "%", r"\sim": "∼", r"\cong": "≅", r"\backsim": "∽",
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ", r"\epsilon": "ε", r"\varepsilon": "ε",
    r"\theta": "θ", r"\lambda": "λ", r"\mu": "μ", r"\pi": "π", r"\rho": "ρ", r"\sigma": "σ",
    r"\tau": "τ", r"\phi": "φ", r"\varphi": "φ", r"\omega": "ω", r"\Omega": "Ω", r"\Sigma": "Σ",
    r"\Pi": "Π", r"\Gamma": "Γ", r"\Theta": "Θ", r"\Lambda": "Λ", r"\Phi": "Φ",
    r"\sum": "Σ", r"\prod": "∏", r"\int": "∫", r"\partial": "∂", r"\nabla": "∇",
    r"\ldots": "…", r"\cdots": "⋯", r"\dots": "…", r"\therefore": "∴", r"\because": "∵",
    r"\{": "{", r"\}": "}", r"\|": "‖", r"\,": " ", r"\;": " ", r"\:": " ", r"\!": "", r"\quad": "  ",
    r"\qquad": "    ", r"\ ": " ", r"\\": "; ",
}
SUPERSCRIPT = str.maketrans("0123456789+-=()nixyabc", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱˣʸᵃᵇᶜ")
SUBSCRIPT = str.maketrans("0123456789+-=()aeoxijn", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓᵢⱼₙ")
_SUP_OK = set("0123456789+-=()nixyabc")
_SUB_OK = set("0123456789+-=()aeoxijn")

_CMD_RE = re.compile(r"\\[A-Za-z]+|\\.")

# Font app (Be Vietnam Pro) có glyph SAI cho vài ký hiệu toán (√ hiện "Ã", ∞/∫ hiện "°") mà Qt vẫn dùng
# vì font "khai báo" có glyph → bọc khối ký hiệu toán (U+2200–U+22FF) trong span dùng font toán học.
_MATH_GLYPH_RE = re.compile(r"[∀-⋿]+")
MATH_GLYPH_FONTS = "'Cambria Math', 'Segoe UI Symbol', 'STIX Two Math', 'Apple Symbols', 'DejaVu Sans'"


def wrap_math_glyphs(html: str) -> str:
    """Bọc ký hiệu toán Unicode trong chuỗi HTML đã escape bằng font hiển thị đúng (√, ∞, ∫, ≤ …)."""
    return _MATH_GLYPH_RE.sub(lambda m: f'<span style="font-family:{MATH_GLYPH_FONTS};">{m.group(0)}</span>', html)


def _read_group(s: str, i: int) -> tuple[str, int]:
    """Đọc 1 nhóm `{...}` (lồng nhau) hoặc 1 ký tự / 1 lệnh tại vị trí i. Trả (nội dung, vị trí kế)."""
    while i < len(s) and s[i] == " ":
        i += 1
    if i >= len(s):
        return "", i
    if s[i] == "{":
        depth, j = 0, i
        while j < len(s):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1:j], j + 1
            j += 1
        return s[i + 1:], len(s)
    if s[i] == "\\":
        m = _CMD_RE.match(s, i)
        if m:
            return m.group(0), m.end()
    return s[i], i + 1


def _wrap(text: str) -> str:
    return text if len(text) <= 1 or re.fullmatch(r"[\w.]+", text) else f"({text})"


def latex_to_unicode(latex: str) -> str:
    s = re.sub(r"\\(?:left|right|big|Big|bigg|Bigg|displaystyle|textstyle)\b\.?", "", latex)
    s = re.sub(r"\\begin\{[a-zA-Z*]+\}(\{[^}]*\})?|\\end\{[a-zA-Z*]+\}", "", s)
    s = s.replace("&", " ")
    out: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\":
            m = _CMD_RE.match(s, i)
            cmd = m.group(0)
            i = m.end()
            if cmd in (r"\frac", r"\dfrac", r"\tfrac"):
                num, i = _read_group(s, i)
                den, i = _read_group(s, i)
                out.append(f"{_wrap(latex_to_unicode(num))}/{_wrap(latex_to_unicode(den))}")
            elif cmd == r"\sqrt":
                index = ""
                if i < len(s) and s[i] == "[":
                    close = s.find("]", i)
                    index, i = s[i + 1:close], close + 1
                body, i = _read_group(s, i)
                prefix = {"3": "∛", "4": "∜"}.get(index, (index.translate(SUPERSCRIPT) if index else "") + "√")
                out.append(f"{prefix}{_wrap(latex_to_unicode(body))}")
            elif cmd in (r"\text", r"\mathrm", r"\textbf", r"\mathbf", r"\textit", r"\mathit", r"\operatorname"):
                body, i = _read_group(s, i)
                out.append(body)
            elif cmd in (r"\overline", r"\bar"):
                body, i = _read_group(s, i)
                out.append(latex_to_unicode(body) + "\u0305")
            elif cmd in (r"\overrightarrow", r"\vec"):
                body, i = _read_group(s, i)
                out.append(latex_to_unicode(body) + "\u20d7")
            elif cmd == r"\widehat" or cmd == r"\hat":
                body, i = _read_group(s, i)
                out.append("∠" + latex_to_unicode(body) if cmd == r"\widehat" else latex_to_unicode(body) + "\u0302")
            else:
                out.append(SYMBOLS.get(cmd, cmd[1:] + (" " if cmd[1:].isalpha() else "")))
        elif ch in "^_":
            body, i = _read_group(s, i + 1)
            body = latex_to_unicode(body).strip()
            allowed, table = (_SUP_OK, SUPERSCRIPT) if ch == "^" else (_SUB_OK, SUBSCRIPT)
            if ch == "^" and body in ("°", "′", "″", "'"):   # 90^\circ → 90°
                out.append(body)
            elif body and set(body) <= allowed:
                out.append(body.translate(table))
            else:
                out.append(f"{ch}({body})" if len(body) > 1 else f"{ch}{body}")
        elif ch in "{}":
            i += 1
        else:
            out.append(ch)
            i += 1
    return re.sub(r" {2,}", " ", "".join(out)).strip()
