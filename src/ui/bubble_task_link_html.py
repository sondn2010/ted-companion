"""Biến câu thoại thuần của bong bóng thành HTML có link "task:<id>" ở tên task (click → popup chi tiết task)."""

from html import escape
from typing import Optional, Sequence

from src.ui.theme import design_tokens as tk

TASK_LINK_SCHEME = "task:"


def linkify_task_titles(text: str, task_links: Sequence[tuple[str, str]]) -> str:
    """task_links: (cụm chữ tên task đúng như trong text, task_id). Mỗi task gắn link ở lần xuất hiện đầu;
    cụm không có trong text / chồng lên link khác bị bỏ qua. Phần còn lại escape + xuống dòng thành <br>."""
    spans: list[tuple[int, int, str]] = []
    for phrase, task_id in sorted(task_links, key=lambda link: -len(link[0])):  # tên dài trước: tránh khớp tên con
        if not phrase or not task_id:
            continue
        start = text.find(phrase)
        end = start + len(phrase)
        if start < 0 or any(start < e and s < end for s, e, _ in spans):
            continue
        spans.append((start, end, task_id))

    parts, cursor = [], 0
    for start, end, task_id in sorted(spans):
        parts.append(_plain_html(text[cursor:start]))
        parts.append(
            f"<a href='{TASK_LINK_SCHEME}{escape(task_id, quote=True)}' "
            f"style='color:{tk.PRIMARY_SOFT}; font-weight:600;'>{_plain_html(text[start:end])}</a>"
        )
        cursor = end
    parts.append(_plain_html(text[cursor:]))
    return "".join(parts)


def task_id_from_href(href: str) -> Optional[str]:
    if href.startswith(TASK_LINK_SCHEME):
        return href[len(TASK_LINK_SCHEME):] or None
    return None


def _plain_html(chunk: str) -> str:
    return escape(chunk).replace("\n", "<br>")
