"""Dựng HTML an toàn cho câu trả lời của Ted / nội dung ôn tập (tập con HTML mà QTextEdit/QLabel hiểu).

Hỗ trợ: công thức LaTeX ($…$, $$…$$, \\(…\\), \\[…\\]), bảng & biểu mẫu markdown, hình vẽ SVG,
tiêu đề, **đậm**, *nghiêng*, `mã`, danh sách (kể cả ô tích ☐/☑), trích dẫn, đường kẻ.

AN TOÀN: mọi văn bản đều được escape TRƯỚC; HTML trong kết quả chỉ do chính module này sinh ra
→ nội dung AI có chứa thẻ HTML vẫn hiện nguyên văn, không bị diễn giải.
"""

from html import escape
import re

from src.ui.rich_content.latex_math_image_renderer import math_html
from src.ui.rich_content.latex_unicode_fallback import wrap_math_glyphs
from src.ui.rich_content.rich_reply_segment_patterns import (
    DISPLAY_MATH_RE,
    FENCE_RE,
    INLINE_MATH_RE,
    RAW_SVG_RE,
    TABLE_SEPARATOR_RE,
    has_rich_markup,
)
from src.ui.rich_content.svg_figure_image_renderer import svg_figure_html
from src.ui.theme import design_tokens as tk

_TOKEN_RE = re.compile("\x00(\\d+)\x00")
_BLOCK_TOKEN_RE = re.compile("^\\s*\x00(\\d+)\x00\\s*$")
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_CHECK_RE = re.compile(r"^\[( |x|X)\]\s+")


class _Segments:
    """Giữ chỗ các đoạn đặc biệt (công thức/hình/mã) bằng \\x00N\\x00 để markdown & escape không đụng vào."""

    def __init__(self):
        self.html: list[str] = []
        self.block: set[int] = set()

    def put(self, html: str, block: bool) -> str:
        self.html.append(html)
        idx = len(self.html) - 1
        if block:
            self.block.add(idx)
            return f"\n\x00{idx}\x00\n"
        return f"\x00{idx}\x00"


def _inline(text: str, seg: _Segments) -> str:
    out = wrap_math_glyphs(escape(text))
    out = re.sub(r"`([^`]+)`", lambda m: f"<code style='background-color:{tk.SURFACE_RAISED};'>{m.group(1)}</code>", out)
    out = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"<b>{m.group(1) or m.group(2)}</b>", out)
    out = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<i>\1</i>", out)
    return _TOKEN_RE.sub(lambda m: seg.html[int(m.group(1))], out)


def _table(rows: list[str], seg: _Segments) -> str:
    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]
    header, body = cells(rows[0]), [cells(r) for r in rows[2:]]
    border = tk.OUTLINE_STRONG
    th = "".join(f"<th bgcolor='{tk.SURFACE_OVERLAY}' style='padding:5px 8px; color:{tk.PRIMARY_SOFT};'>"
                 f"{_inline(c, seg)}</th>" for c in header)
    trs = "".join("<tr>" + "".join(f"<td style='padding:5px 8px;'>{_inline(c, seg) or '&nbsp;'}</td>" for c in r)
                  + "</tr>" for r in body)
    return (f"<table border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse; "
            f"border-color:{border}; margin:6px 0;'><tr>{th}</tr>{trs}</table>")


def _list_item(content: str, seg: _Segments) -> str:
    check = _CHECK_RE.match(content)
    if check:
        box = "☑" if check.group(1).lower() == "x" else "☐"
        return f"<li>{box} {_inline(content[check.end():], seg)}</li>"
    return f"<li>{_inline(content, seg)}</li>"


def _blocks(text: str, seg: _Segments) -> str:
    lines = text.split("\n")
    out: list[str] = []
    para: list[str] = []
    i = 0

    def flush():
        if para:
            out.append(f"<p style='margin:2px 0;'>{'<br>'.join(_inline(p, seg) for p in para)}</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        token = _BLOCK_TOKEN_RE.match(line)
        if token and int(token.group(1)) in seg.block:
            flush()
            out.append(seg.html[int(token.group(1))])
        elif not stripped:
            flush()
        elif stripped.startswith("|") and i + 1 < len(lines) and TABLE_SEPARATOR_RE.match(lines[i + 1]):
            flush()
            rows = [line, lines[i + 1]]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(_table(rows, seg))
            continue
        elif _HEADING_RE.match(stripped):
            flush()
            level, title = _HEADING_RE.match(stripped).groups()
            size = {1: 17, 2: 16, 3: 15, 4: 14}[len(level)]
            out.append(f"<p style='margin:8px 0 2px 0; font-size:{size}px;'><b>{_inline(title, seg)}</b></p>")
        elif re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            flush()
            out.append("<hr>")
        elif stripped.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(_inline(lines[i].strip()[1:].strip(), seg))
                i += 1
            out.append(f"<table cellspacing='0' cellpadding='0' style='margin:4px 0;'><tr>"
                       f"<td width='3' bgcolor='{tk.SECONDARY}'></td><td style='padding:4px 10px; color:{tk.TEXT_MUTED};'>"
                       f"{'<br>'.join(quote)}</td></tr></table>")
            continue
        elif _LIST_RE.match(line):
            flush()
            ordered = _LIST_RE.match(line).group(2)[0].isdigit()
            items = []
            while i < len(lines) and _LIST_RE.match(lines[i]) and _LIST_RE.match(lines[i]).group(2)[0].isdigit() == ordered:
                items.append(_list_item(_LIST_RE.match(lines[i]).group(3), seg))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag} style='margin:2px 0;'>{''.join(items)}</{tag}>")
            continue
        else:
            para.append(line)
        i += 1
    flush()
    return "".join(out)


def rich_reply_html(text: str, *, max_width: int = 360, color: str = tk.TEXT) -> str:
    seg = _Segments()

    def fence(m: re.Match) -> str:
        lang, body = m.group(1).lower(), m.group(2)
        if lang == "svg" or body.lstrip().lower().startswith("<svg"):
            return seg.put(svg_figure_html(body, max_width), block=True)
        if lang in ("math", "latex", "tex"):
            return seg.put(math_html(body, display=True, color=color, max_width=max_width), block=True)
        code = escape(body.rstrip("\n"))
        return seg.put(f"<pre style='background-color:{tk.SURFACE_RAISED}; padding:8px;'>{code}</pre>", block=True)

    work = text.replace("\r\n", "\n").replace("\x00", "")
    work = FENCE_RE.sub(fence, work)
    work = RAW_SVG_RE.sub(lambda m: seg.put(svg_figure_html(m.group(0), max_width), block=True), work)
    work = DISPLAY_MATH_RE.sub(
        lambda m: seg.put(math_html(m.group(1) or m.group(2), display=True, color=color, max_width=max_width), True), work)
    work = INLINE_MATH_RE.sub(
        lambda m: seg.put(math_html(m.group(1) or m.group(2), display=False, color=color, max_width=max_width), False), work)
    return _blocks(work, seg)


def reply_body_html(text: str, *, max_width: int = 360) -> str:
    """HTML thân câu trả lời: giàu định dạng khi có markup, còn lại giữ chữ thuần như trước (escape + xuống dòng)."""
    if has_rich_markup(text):
        return rich_reply_html(text, max_width=max_width)
    return wrap_math_glyphs(escape(text)).replace("\n", "<br>")
