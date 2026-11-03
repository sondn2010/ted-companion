"""Kéo lịch từ Hermes (profile work) → validate → thay cửa sổ cache. Thất bại bất kỳ → giữ nguyên cache cũ."""

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from src.bridge.hermes_json_contract_request import request_json
from src.engines.work.calendar_contract_schemas import CalendarResponse, to_utc
from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventRepository
from src.engines.work.local_timezone_name import local_timezone_name
from src.modules_runtime.prompt_template_renderer import load_prompt

logger = logging.getLogger("ted")
FETCHED_AT_KEY = "work.calendar_fetched_at"
EMPTY_STREAK_KEY = "work.calendar_empty_streak"
CALENDAR_REQUEST_TIMEOUT_SECS = 60.0
EMPTY_REPLIES_TO_ACCEPT = 2   # lần trả lời rỗng liên tiếp mới tin là lịch thật sự trống (1 lần có thể là MCP lỗi)


def calendar_window(now_local: datetime, days_ahead: int) -> tuple[datetime, datetime]:
    """[00:00 local hôm nay, 00:00 local của ngày thứ days_ahead+1) — aware theo múi giờ local."""
    local = now_local.astimezone()
    start = datetime.combine(local.date(), time.min, tzinfo=local.tzinfo)
    end = datetime.combine(local.date() + timedelta(days=days_ahead), time.min, tzinfo=local.tzinfo)
    return start, end


class CalendarSyncService:
    def __init__(self, manifest, ctx, repo: CalendarEventRepository):
        self._manifest = manifest
        self._ctx = ctx
        self._repo = repo
        self._in_flight = False
        self.last_ok: Optional[bool] = None  # None = chưa thử lần nào trong phiên này

    def fetched_at(self) -> Optional[datetime]:
        raw = self._ctx.kv.get(FETCHED_AT_KEY) if self._ctx.kv else None
        try:
            return datetime.fromisoformat(raw) if raw else None
        except ValueError:
            return None

    def _empty_streak(self) -> int:
        try:
            return int(self._ctx.kv.get(EMPTY_STREAK_KEY) or 0)
        except ValueError:
            return 0

    async def sync(self) -> bool:
        """True nếu cache đã được thay bằng dữ liệu mới. Bỏ qua nếu đang có 1 lần sync khác chạy."""
        if self._in_flight:
            return False
        self._in_flight = True
        try:
            return await self._sync_once()
        except Exception:
            logger.exception("Đồng bộ lịch lỗi, giữ cache cũ")
            self.last_ok = False
            return False
        finally:
            self._in_flight = False

    async def _sync_once(self) -> bool:
        settings = self._manifest.settings
        start, end = calendar_window(datetime.now().astimezone(), int(settings.get("calendar_days_ahead", 7)))
        prompt = load_prompt(self._manifest, "calendar_request", {
            "from": start.isoformat(), "to": end.isoformat(), "tz": local_timezone_name(settings.get("timezone")),
        })
        pool = self._ctx.client_pool
        client = pool.for_module(self._manifest.id) if pool else None
        if not prompt or client is None:
            self.last_ok = False
            return False
        response = await request_json(client, prompt, CalendarResponse, timeout=CALENDAR_REQUEST_TIMEOUT_SECS)
        if response is None:
            self.last_ok = False
            return False
        now_utc = datetime.now(timezone.utc)
        start_utc, end_utc = to_utc(start), to_utc(end)
        in_window = [e for e in response.events if start_utc <= e.start < end_utc]
        if not in_window and self._repo.has_upcoming_timed(now_utc):
            streak = self._empty_streak() + 1
            self._ctx.kv.set(EMPTY_STREAK_KEY, str(streak))
            if streak < EMPTY_REPLIES_TO_ACCEPT:
                logger.warning("Hermes trả lịch rỗng nhưng cache còn họp sắp tới → giữ cache, chờ xác nhận lần sau")
                self.last_ok = False
                return False
        self._ctx.kv.set(EMPTY_STREAK_KEY, "0")
        count = self._repo.replace_window(start_utc, end_utc, response.events, now_utc)
        self._repo.prune(start_utc - timedelta(days=1), end_utc)
        self._ctx.kv.set(FETCHED_AT_KEY, now_utc.isoformat())
        self.last_ok = True
        logger.info("Đã đồng bộ %d sự kiện lịch", count)
        return True
