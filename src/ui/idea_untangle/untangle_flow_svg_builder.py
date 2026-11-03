"""Dựng sơ đồ luồng (SVG tĩnh) từ flow_steps: hộp xuống dòng ≤3 dòng, mũi tên, bước lỗ hổng tô đỏ + "⚠".

Thuần chuỗi, mọi chữ do AI sinh đều XML-escape. Chạy qua svg_figure_image_renderer.render_svg_png để ra PNG.
Rỗng → build_flow_fallback_html (danh sách đánh số).
"""

import textwrap
from dataclasses import dataclass
from html import escape
from typing import Collection, Sequence

WIDTH = 320
BOX_X, BOX_W = 20, 280
LINE_H, PAD_Y, ARROW_H = 16, 8, 18
CHARS_PER_LINE = 34
MAX_LINES = 3


@dataclass(frozen=True)
class FlowColors:
    box_fill: str = "#EAF6FD"
    box_stroke: str = "#00ADEF"
    gap_fill: str = "#FDECEA"
    gap_stroke: str = "#D93025"
    text: str = "#1B2733"
    arrow: str = "#5B6573"


def _wrap(text: str) -> list[str]:
    lines = textwrap.wrap(text, CHARS_PER_LINE, break_long_words=True) or [""]
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        lines[-1] = lines[-1][: CHARS_PER_LINE - 1] + "…"
    return lines


def build_flow_svg(steps: Sequence[str], gap_steps: Collection[int] = (), colors: FlowColors = FlowColors()) -> str:
    """gap_steps = số thứ tự 1-based các bước có lỗ hổng. Không có bước → chuỗi rỗng."""
    if not steps:
        return ""
    parts, y = [], 10
    for idx, step in enumerate(steps, start=1):
        is_gap = idx in gap_steps
        lines = _wrap(f"{idx}. {step}")
        height = PAD_Y * 2 + LINE_H * len(lines)
        fill, stroke = (colors.gap_fill, colors.gap_stroke) if is_gap else (colors.box_fill, colors.box_stroke)
        parts.append(f'<rect x="{BOX_X}" y="{y}" width="{BOX_W}" height="{height}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        for n, line in enumerate(lines):
            ty = y + PAD_Y + LINE_H * (n + 1) - 4
            parts.append(f'<text x="{BOX_X + 10}" y="{ty}" font-size="12" font-family="sans-serif" fill="{colors.text}">{escape(line)}</text>')
        if is_gap:
            parts.append(f'<text x="{BOX_X + BOX_W - 8}" y="{y + PAD_Y + LINE_H - 4}" font-size="13" text-anchor="end" fill="{colors.gap_stroke}">⚠</text>')
        y += height
        if idx < len(steps):
            mid = BOX_X + BOX_W // 2
            parts.append(f'<line x1="{mid}" y1="{y}" x2="{mid}" y2="{y + ARROW_H - 4}" stroke="{colors.arrow}" stroke-width="1.5"/>')
            parts.append(f'<polygon points="{mid - 5},{y + ARROW_H - 8} {mid + 5},{y + ARROW_H - 8} {mid},{y + ARROW_H}" fill="{colors.arrow}"/>')
            y += ARROW_H
    total = y + 10
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{total}" viewBox="0 0 {WIDTH} {total}">{"".join(parts)}</svg>'


def build_flow_fallback_html(steps: Sequence[str], gap_steps: Collection[int] = ()) -> str:
    """Khi không vẽ được SVG: danh sách đánh số, bước lỗ hổng đánh dấu ⚠."""
    items = "".join(f"<li>{escape(s)}{' ⚠' if i in gap_steps else ''}</li>" for i, s in enumerate(steps, start=1))
    return f"<ol>{items}</ol>"
