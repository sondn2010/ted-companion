"""Khối "việc đang làm + việc Khẩn cấp & Quan trọng (Q1)" nối sau câu động viên khi click đơn lên pet (local, không gọi Hermes)."""

from typing import Optional, Sequence

from src.core.focus_engine import FocusState
from src.core.i18n import tr
from src.engines.work.daily_briefing_builder import sanitize_untrusted_text

MAX_URGENT_SHOWN = 3
OPEN_STATUSES = ("todo", "in_progress")


def pick_current_task(focus_engine, open_tasks: Sequence) -> tuple[str, Optional[str]]:
    """(tên, task_id) việc đang làm: phiên Deep Work đang chạy/tạm dừng → task của phiên;
    không thì task "in_progress" sửa gần nhất (open_tasks đã xếp updated_at giảm dần). Không có → ("", None)."""
    if focus_engine is not None and focus_engine.state in (FocusState.DEEP_WORK_RUNNING, FocusState.PAUSED):
        return focus_engine.active_task_title or "", focus_engine.active_task_id
    task = next((t for t in open_tasks if t.status == "in_progress"), None)
    return (task.title, task.id) if task is not None else ("", None)


def compose_task_status_summary(
    current_title: str, current_id: Optional[str], open_tasks: Sequence
) -> tuple[str, list[tuple[str, str]]]:
    """→ (text nhiều dòng, task_links cho bubble). Q1 bỏ việc đang làm (tránh lặp), xếp theo matrix_order, tối đa 3 tên."""
    links: list[tuple[str, str]] = []
    current = sanitize_untrusted_text(current_title or "")
    if current:
        lines = [tr("pet_click_current_task", title=current)]
        if current_id:
            links.append((current, current_id))
    else:
        lines = [tr("pet_click_no_current_task")]

    urgent = sorted(
        (t for t in open_tasks if t.quadrant == 1 and t.status in OPEN_STATUSES and t.id != current_id),
        key=lambda t: t.matrix_order,
    )
    if not urgent:
        lines.append(tr("pet_click_no_urgent_tasks"))
        return "\n".join(lines), links

    lines.append(tr("pet_click_urgent_header", count=len(urgent)))
    for task in urgent[:MAX_URGENT_SHOWN]:
        title = sanitize_untrusted_text(task.title)
        lines.append(f"• {title}")
        links.append((title, task.id))
    if len(urgent) > MAX_URGENT_SHOWN:
        lines.append(tr("pet_click_urgent_more", count=len(urgent) - MAX_URGENT_SHOWN))
    return "\n".join(lines), links


def build_task_status_summary(task_db, focus_engine) -> tuple[str, list[tuple[str, str]]]:
    open_tasks = [t for t in task_db.list_tasks(include_done=False) if t.status in OPEN_STATUSES]
    title, task_id = pick_current_task(focus_engine, open_tasks)
    return compose_task_status_summary(title, task_id, open_tasks)
