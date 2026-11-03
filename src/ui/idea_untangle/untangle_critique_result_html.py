"""UntangleCritique → HTML cho khung chat. Mọi chữ do AI sinh đều được escape; sơ đồ luồng dựng từ chữ đã escape."""

from html import escape
from typing import List

from src.core.i18n import tr
from src.core.idea_untangle.untangle_critique_contract_schemas import UntangleCritique
from src.ui.idea_untangle.untangle_flow_svg_builder import build_flow_fallback_html, build_flow_svg
from src.ui.theme.design_tokens import PRIMARY_SOFT, TEXT, WARNING

FLOW_MAX_WIDTH = 340


def _flow_html(steps: List[str], gap_steps: set) -> str:
    """Sơ đồ SVG → PNG; không vẽ được thì rơi về danh sách đánh số."""
    from src.ui.rich_content.svg_figure_image_renderer import render_svg_png, svg_figure_html
    svg = build_flow_svg(steps, gap_steps)
    try:
        ok = bool(svg) and render_svg_png(svg, FLOW_MAX_WIDTH) is not None
    except Exception:
        ok = False
    return svg_figure_html(svg, FLOW_MAX_WIDTH) if ok else build_flow_fallback_html(steps, gap_steps)


def _heading(key: str, color: str = PRIMARY_SOFT) -> str:
    return f"<p style='color:{color}; margin-bottom:0;'><b>{escape(tr(key))}</b></p>"


def _bullets(items: List[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul>" if items else ""


def critique_html(c: UntangleCritique) -> str:
    gap_steps = {g.step for g in c.logic_gaps if g.step is not None}
    parts = [f"<div style='color:{TEXT};'>", _heading("untangle_critique_summary"),
             f"<p>{escape(c.summary)}</p>" if c.summary else "", _flow_html(c.flow_steps, gap_steps)]
    if c.logic_gaps:
        parts.append(_heading("untangle_critique_gaps", WARNING))
        items = []
        for g in c.logic_gaps:
            where = f"<b>{escape(tr('untangle_gap_step', n=g.step))}:</b> " if g.step is not None else ""
            items.append(f"<li>{where}{escape(g.issue)}"
                         + (f"<br><i>{escape(g.question)}</i>" if g.question else "") + "</li>")
        parts.append("<ul>" + "".join(items) + "</ul>")
    if c.assumptions:
        parts += [_heading("untangle_critique_assumptions"), _bullets(c.assumptions)]
    if c.new_angles:
        parts += [_heading("untangle_critique_angles"), _bullets(c.new_angles)]
    if c.next_step:
        parts += [_heading("untangle_critique_next", PRIMARY_SOFT), f"<p><b>{escape(c.next_step)}</b></p>"]
    parts.append("</div>")
    return "".join(parts)


def notes_text(c: UntangleCritique) -> str:
    """Nội dung ghi vào Task.notes: tóm tắt + bước tiếp theo."""
    return c.summary + (f"\n➜ {c.next_step}" if c.next_step else "")
