"""Dùng chung cho mọi outbox gửi OpenAI-compatible API: phát hiện mất kết nối + lùi lịch 5 → 60 phút."""

from datetime import datetime, timedelta
from typing import Optional

from src.bridge.openai_client import OpenAIUnavailableError

BACKOFF_BASE_MINS = 5
BACKOFF_MAX_MINS = 60


class OpenAIOfflineProbe:
    """Bọc client để biết lần gọi hỏng do mất kết nối (request_json trả None cả khi offline lẫn khi sai hợp đồng)."""

    def __init__(self, client):
        self._client = client
        self.offline = False

    async def complete_text(self, messages, timeout: float = 60.0) -> str:
        try:
            return await self._client.complete_text(messages, timeout=timeout)
        except OpenAIUnavailableError:
            self.offline = True
            raise


class OpenAIOfflineBackoff:
    """Đếm số lần offline liên tiếp → thời điểm được thử lại (gấp đôi mỗi lần, trần 60 phút)."""

    def __init__(self) -> None:
        self.streak = 0
        self.next_try: Optional[datetime] = None

    def blocked(self, now: datetime) -> bool:
        return self.next_try is not None and now < self.next_try

    def on_offline(self, now: datetime) -> None:
        self.streak += 1
        delay = min(BACKOFF_BASE_MINS * 2 ** (self.streak - 1), BACKOFF_MAX_MINS)
        self.next_try = now + timedelta(minutes=delay)

    def reset(self) -> None:
        self.streak, self.next_try = 0, None


# Backward compatibility aliases
OfflineProbe = OpenAIOfflineProbe
OfflineBackoff = OpenAIOfflineBackoff
