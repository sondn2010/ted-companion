"""Gửi 1 dòng [ROCK_UPDATE] tới Hermes (best-effort) để profile ghi memory. Không đụng lịch sử chat."""

import logging

from src.bridge.openai_client import OpenAIRequestRejectedError as HermesRequestRejectedError, OpenAIUnavailableError as HermesUnavailableError
from src.engines.work.daily_briefing_builder import sanitize_untrusted_text

logger = logging.getLogger("ted")
ROCK_SYNC_TIMEOUT_SECS = 15.0


def format_rock_update(action: str, title: str, age_days: int) -> str:
    return f"[ROCK_UPDATE] {action}: {sanitize_untrusted_text(title)} ({age_days} ngày)"


async def send_rock_update(client, line: str) -> bool:
    """True nếu Hermes nhận; lỗi mạng chỉ ghi log (Rock đã lưu local, không cần retry)."""
    if client is None:
        return False
    try:
        await client.complete_text([{"role": "user", "content": line}], timeout=ROCK_SYNC_TIMEOUT_SECS)
        return True
    except (HermesUnavailableError, HermesRequestRejectedError) as exc:
        logger.info("Không sync được Rock tới Hermes: %s", exc)
        return False
