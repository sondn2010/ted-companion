"""Ted nhắc việc quan trọng kế tiếp khi bắt đầu phiên deep work (text local, không gọi Hermes → tức thì, offline vẫn chạy)."""

import logging
from typing import Optional, Sequence

from src.core.background_task_spawner import spawn_background_task
from src.core.tts_service import tts_service
from src.engines.work.daily_briefing_builder import sanitize_untrusted_text

logger = logging.getLogger("ted")

ANNOUNCE_BUBBLE_MS = 10_000
ANNOUNCE_MOOD = "FOCUS"


def compose_next_task_message(
    current_task_id: Optional[str],
    current_title: str,
    ranked_open_tasks: Sequence,
) -> str:
    """ranked_open_tasks: Task đã xếp hạng Q1 → Q2 (đọc .id/.title/.quadrant). Ted xưng "em", gọi "anh"."""
    current = sanitize_untrusted_text(current_title or "") or "phiên này"
    ranked = list(ranked_open_tasks)

    if not ranked:
        return f"Không còn việc Q1/Q2, anh tập trung vào {current} nhé."

    if current_task_id and ranked[0].id == current_task_id:  # chỉ khen khi đúng việc xếp hạng đầu
        msg = f"Anh đang làm {current} – đúng việc quan trọng nhất rồi!"
        following = next((t for t in ranked if t.id != current_task_id), None)
        if following is not None:
            msg += f" Sau đó em gợi ý làm {sanitize_untrusted_text(following.title)} nhé."
        return msg

    top = ranked[0]
    return f"Gợi ý: Q{top.quadrant} còn {sanitize_untrusted_text(top.title)}, anh cân nhắc làm trước nhé."


def next_task_links(current_task_id: Optional[str], current_title: str, ranked_open_tasks: Sequence) -> list[tuple[str, str]]:
    """(tên task đúng như compose_next_task_message viết ra, task_id) để bubble gắn link mở chi tiết task.
    Tên không xuất hiện trong câu thoại thì bubble tự bỏ qua."""
    links = [(sanitize_untrusted_text(t.title), t.id) for t in ranked_open_tasks]
    if current_task_id:
        links.append((sanitize_untrusted_text(current_title or ""), current_task_id))
    return [(title, task_id) for title, task_id in links if title and task_id]


def announce(ctx, text: str, speak: bool = True, task_links: Sequence[tuple[str, str]] = ()) -> None:
    """Hiện bubble 10s và đọc to (speak=False khi đang họp; TTS tự bỏ qua nếu tắt). Lỗi UI/TTS không được làm hỏng phiên focus.
    Bubble đang có nút hành động (nhắc họp...) → bỏ qua hẳn, không đè mất nút."""
    bubble = getattr(ctx, "bubble", None)
    if bubble is not None:
        try:
            if bubble.has_pending_actions():
                return

            bubble.show_message(text, mood=ANNOUNCE_MOOD, timeout_ms=ANNOUNCE_BUBBLE_MS, task_links=task_links)
        except Exception:
            logger.exception("Không hiện được bubble nhắc việc kế tiếp")
    if not speak:
        return
    coro = tts_service.speak(text)
    try:
        spawn_background_task(coro, "deep-work-next-task-speak")
    except RuntimeError:  # không có event loop (test đồng bộ)
        coro.close()
        logger.debug("Không có event loop, bỏ qua TTS nhắc việc kế tiếp")
