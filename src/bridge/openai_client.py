import logging
import re
from typing import Callable, Optional

import httpx
import openai
from openai import AsyncOpenAI

from src.bridge.mood_tag_stream_parser import MoodTagStreamParser
from src.core.connection_registry_and_settings_migration import OpenAIConnection
from src.core.models import db

logger = logging.getLogger("ted")

SYSTEM_FALLBACK_PROMPT = """Bạn là Ted, một người bạn nhỏ ấm áp, tinh tế đồng hành cùng người dùng trên góc màn hình Desktop.
Sứ mệnh của bạn là giúp người dùng giữ trạng thái Deep Work (Tập trung sâu), cất giữ các ý tưởng gây xao nhãng vào Bãi đỗ (Parking Lot), và tổng kết công việc hằng ngày.
Quy tắc bắt buộc:
1. Mọi câu trả lời PHẢI bắt đầu bằng đúng 1 thẻ cảm xúc: [MOOD:IDLE], [MOOD:FOCUS], [MOOD:GENTLE_NUDGE], [MOOD:CHEER], hoặc [MOOD:REST].
2. Khi người dùng đang trong phiên tập trung (DEEP_WORK_RUNNING), trả lời ngắn gọn tối đa 2 câu để bảo vệ sự tập trung của họ.
3. Xưng "mình" hoặc "Ted", gọi người dùng là "bạn", giọng văn khích lệ, không bao giờ phán xét."""

# Persona của khung chat theo engine của module: "work" giữ nguyên hành vi cũ; coach không gửi system prompt
# dự phòng và dùng header trạng thái gọn, không có analytics công việc.
PERSONA_WORK = "work"
COACH_HISTORY_MESSAGES = 30   # phỏng vấn onboarding ~8 câu hỏi ≈ 16+ tin nhắn, cửa sổ 10 sẽ làm rơi tên/mục tiêu
WORK_HISTORY_MESSAGES = 10
ONBOARDING_TAG = "[TED_ONBOARDING]"

CHAT_TIMEOUT_SECS = 25.0
PING_TIMEOUT_SECS = 8.0

# Thẻ giao thức ([TED_SYNC_PLAN], [TED_STATE: ...]) và khối <json> không được lọt vào lịch sử chat
_PROTOCOL_TAG_RE = re.compile(r"\[TED_[A-Z_]+(?::[^\]]*)?\]")
_JSON_BLOCK_RE = re.compile(r"<json>.*?</json>", re.S)


class OpenAIUnavailableError(Exception):
    """Máy chủ OpenAI-compatible không phản hồi được (offline, timeout, sai API key, lỗi HTTP)."""


class OpenAIRequestRejectedError(Exception):
    """Máy chủ OpenAI-compatible đang online nhưng từ chối yêu cầu (HTTP 4xx trừ 401/408/429). KHÔNG phải OpenAIUnavailableError."""


# Backward compatibility aliases
HermesUnavailableError = OpenAIUnavailableError
HermesRequestRejectedError = OpenAIRequestRejectedError

_TRANSIENT_STATUS = {408, 429}


def sanitize_for_history(text: str) -> str:
    return _PROTOCOL_TAG_RE.sub("", _JSON_BLOCK_RE.sub("", text)).strip()


class OpenAIBrainClient:
    """
    Giao tiếp với API Server chuẩn OpenAI cho MỘT kết nối.
    Mỗi kết nối có lịch sử chat riêng (chat công việc không lẫn sang gia sư của con).
    """

    def __init__(self, connection: OpenAIConnection, http_client: Optional[httpx.AsyncClient] = None):
        self.connection = connection
        self.history = [{"role": "system", "content": SYSTEM_FALLBACK_PROMPT}]
        self._http_client = http_client
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                base_url=self.connection.base_url,
                api_key=self.connection.api_key or "no-key",
                timeout=CHAT_TIMEOUT_SECS,
                max_retries=0,  # tự quản lý retry ở tầng trên
                http_client=self._http_client,
            )
        return self._client

    def _mask(self, text: str) -> str:
        key = self.connection.api_key
        return text.replace(key, "***") if key else text

    async def stream_chat(
        self,
        user_message: str,
        current_context: dict,
        on_mood_change: Callable[[str], None],
        on_token: Callable[[str], None],
        persona: str = PERSONA_WORK,
        resume_mood: Optional[str] = None,
    ) -> str:
        """resume_mood: mood trả lại sau khi trả lời xong nếu AI không gửi thẻ [MOOD:...] (vd FOCUS khi đang phiên)."""
        is_work = persona == PERSONA_WORK
        if is_work:
            analytics = db.get_today_analytics()
            context_header = (
                f"[TED_STATE: status={current_context.get('status')}, "
                f"active_task='{current_context.get('task')}', "
                f"remaining_mins={current_context.get('remaining_mins')}, "
                f"today_completed_pomodoros={analytics['completed_sessions']}, "
                f"today_focus_mins={analytics['total_focus_minutes']}]\n"
            )
        else:
            context_header = f"[TED_STATE: status={current_context.get('status')}]\n"

        # Work: system prompt ở đầu + 10 lượt gần nhất. Coach: không system prompt, cửa sổ rộng hơn cho onboarding.
        head = self.history[:1] if is_work else []
        window = WORK_HISTORY_MESSAGES if is_work else COACH_HISTORY_MESSAGES
        messages = head + self.history[1:][-window:] + [{"role": "user", "content": context_header + user_message}]
        parser = MoodTagStreamParser()
        full_text = ""
        mood_from_reply = False
        on_mood_change("IDLE")   # đang chờ phản hồi → avatar về trạng thái idle

        def emit(mood: Optional[str], text: str):
            nonlocal full_text, mood_from_reply
            if mood:
                mood_from_reply = True
                on_mood_change(mood)
            if text:
                full_text += text
                on_token(text)

        try:
            stream = await self._get_client().chat.completions.create(
                model=self.connection.model,
                messages=messages,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    emit(*parser.feed(delta))
            emit(*parser.finish())
            if not mood_from_reply and resume_mood:
                on_mood_change(resume_mood)
            self._remember(user_message, full_text)
            return full_text

        except Exception as exc:
            # Chế độ Fallback thân thiện khi chưa kết nối được
            logger.warning("stream_chat [%s] lỗi: %s", self.connection.id, self._mask(str(exc)))
            on_mood_change("GENTLE_NUDGE")
            from src.core.offline_guide_engine import match_offline_guide, get_offline_starter_menu
            matched = match_offline_guide(user_message)
            if matched:
                _, answer = matched
                clean_ans = re.sub(r"<[^>]+>", "", answer)
                fallback = f"Hiện chưa kết nối được tới Não AI '{self.connection.name}'. Nhưng đừng lo, Ted giải thích ngay cho bạn nè:\n\n{clean_ans}"
            else:
                menu = get_offline_starter_menu()
                clean_menu = re.sub(r"<[^>]+>", "", menu)
                fallback = (
                    f"Hiện mình chưa kết nối được tới Não AI '{self.connection.name}'.\n\n"
                    f"{clean_menu}"
                )
            on_token(fallback)
            return fallback

    def _remember(self, user_message: str, reply: str):
        user_clean = sanitize_for_history(user_message)
        if not user_clean and user_message.lstrip().startswith(ONBOARDING_TAG):
            # Lượt mở đầu phỏng vấn phải ở lại lịch sử để biết learner đang onboarding
            user_clean = user_message.strip()
        if not user_clean:
            return  # lượt thuần giao thức: không ghi vào lịch sử chat
        reply_clean = sanitize_for_history(reply)
        if not reply_clean:
            return  # không lưu lượt assistant rỗng (một số server từ chối content "")
        self.history.append({"role": "user", "content": user_clean})
        self.history.append({"role": "assistant", "content": reply_clean})

    async def complete_text(self, messages: list[dict], timeout: float = 60.0) -> str:
        """Gọi non-stream, không chạm lịch sử chat. Lỗi mạng/HTTP → OpenAIUnavailableError."""
        try:
            resp = await self._get_client().chat.completions.create(
                model=self.connection.model,
                messages=messages,
                timeout=timeout,
            )
        except openai.APIStatusError as exc:
            if exc.status_code == 401:
                raise OpenAIUnavailableError("Sai API key") from exc
            detail = self._mask(f"HTTP {exc.status_code}: {exc.message}")
            if exc.status_code in _TRANSIENT_STATUS or exc.status_code >= 500:
                raise OpenAIUnavailableError(detail) from exc
            # 400/403/404/413/422…: Server từ chối chính yêu cầu này → thử lại/đợi online cũng vô ích
            raise OpenAIRequestRejectedError(detail) from exc
        except Exception as exc:  # mất mạng, InvalidURL, phản hồi không phải JSON...
            raise OpenAIUnavailableError(self._mask(f"{type(exc).__name__}: {exc}")) from exc
        choices = getattr(resp, "choices", None)
        if not choices:
            return ""
        return choices[0].message.content or ""

    async def ping(self) -> tuple[bool, str]:
        """Kiểm tra kết nối: models.list(), nếu endpoint không hỗ trợ (404) thì thử chat 1 lượt."""
        try:
            await self._get_client().with_options(timeout=PING_TIMEOUT_SECS).models.list()
            return True, f"Kết nối '{self.connection.name}' hoạt động tốt."
        except openai.APIStatusError as exc:
            if exc.status_code == 401:
                return False, "Sai API key."
            if exc.status_code != 404:
                return False, self._mask(f"Không nhận được phản hồi từ Não AI (HTTP {exc.status_code}).")
        except Exception as exc:
            return False, self._mask(f"Không kết nối được tới '{self.connection.name}' ({type(exc).__name__}).")
        try:
            await self.complete_text([{"role": "user", "content": "ping"}], timeout=PING_TIMEOUT_SECS)
            return True, f"Kết nối '{self.connection.name}' hoạt động tốt."
        except (OpenAIUnavailableError, OpenAIRequestRejectedError) as exc:
            return False, f"Không kết nối được tới '{self.connection.name}': {exc}"

    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None


# Backward compatibility aliases
HermesBrainClient = OpenAIBrainClient
HermesClient = OpenAIBrainClient
