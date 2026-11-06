"""Luồng briefing: gom dữ liệu → hiện bản local ngay → nâng cấp bằng Hermes (10s) nếu được, lỗi thì giữ bản local."""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from shiboken6 import isValid

from src.bridge.openai_client import OpenAIRequestRejectedError as HermesRequestRejectedError, OpenAIUnavailableError as HermesUnavailableError, sanitize_for_history
from src.bridge.mood_tag_stream_parser import MOOD_TAG_RE
from src.core.background_task_spawner import spawn_background_task
from src.core.tts_service import tts_service
from src.engines.work.daily_briefing_builder import (
    BriefingInput,
    briefing_prompt_values,
    build_local_briefing_text,
)
from src.engines.work.email_digest_fetcher import fetch_email_digest
from src.engines.work.meeting_overlap_gate import is_in_meeting
from src.engines.work.rock_model_and_repository import RockRepository, rock_age_days
from src.engines.work.work_briefing_due_window import MIDDAY, MORNING, slot_boundary
from src.engines.work.work_briefing_run_guard import (
    LATE_RESULT_SECS,
    PIPELINE_DEADLINE_SECS,
    email_since,
    speech_suppressed,
)
from src.engines.work.work_briefing_slot_content_selection import events_for_slot, open_task_titles_for_slot
from src.modules_runtime.prompt_template_renderer import load_prompt

logger = logging.getLogger("ted")

MAX_ROCKS = 3
BRIEFING_BUBBLE_MS = 12_000
HERMES_BRIEFING_TIMEOUT_SECS = 10.0


def today_calendar_events(db_engine, only_unfinished: bool = False) -> list[tuple[datetime, str]]:
    """Sự kiện lịch hôm nay từ cache của phase 05 (repo.today() → obj có start_at/title). Chưa có → [].
    only_unfinished: bỏ họp đã kết thúc (briefing bắt kịp muộn không liệt kê họp đã qua)."""
    try:
        from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventRepository, event_end
    except ModuleNotFoundError:
        return []
    try:
        now = datetime.now(timezone.utc)
        rows = CalendarEventRepository(db_engine).today()
        return [(e.start_at, e.title) for e in rows if not e.all_day and (not only_unfinished or event_end(e) >= now)]
    except Exception:
        logger.exception("Không đọc được lịch hôm nay cho briefing")
        return []


@dataclass
class _Run:
    """Trạng thái 1 lần chạy nền: text = bản cuối sẽ đọc, shown = chữ ta kỳ vọng bubble đang hiện, started = mốc monotonic."""

    text: str
    shown: str
    started: float

    def elapsed(self) -> float:
        return time.monotonic() - self.started


class WorkBriefingFlow:
    def __init__(self, manifest, ctx, db_engine, rocks: RockRepository, calendar_repo=None):
        self._manifest = manifest
        self._ctx = ctx
        self._db_engine = db_engine
        self._rocks = rocks
        self._calendar_repo = calendar_repo  # None → không biết có đang họp không → vẫn đọc to
        self._generation = 0  # chỉ pipeline của lần start() mới nhất được cập nhật bubble / đọc to

    def _client(self):
        return self._ctx.client_pool.for_module(self._manifest.id) if self._ctx.client_pool else None

    def gather(self, slot: str = MORNING) -> BriefingInput:
        now = datetime.now().astimezone()
        stale_days = int(self._manifest.settings.get("rock_stale_days", 3))
        stale = self._rocks.stale(now, stale_days)[:MAX_ROCKS]
        events = events_for_slot(today_calendar_events(self._db_engine, only_unfinished=True), slot, slot_boundary(self._manifest.settings))
        return BriefingInput(
            tasks=open_task_titles_for_slot(self._db_engine, now.date(), slot),
            events=events,
            stale_rocks=[(r.title, rock_age_days(r, now)) for r in stale],
            slot=slot,
        )

    def start(self, slot: str = MORNING, previous_at: Optional[datetime] = None, now: Optional[datetime] = None) -> None:
        """Hiện bản local ngay (offline vẫn dùng được) rồi ở nền: email → Hermes viết lại → đọc to 1 lần.
        previous_at: mốc briefing trước (trưa quét email từ đó). Mỗi lần start tăng thế hệ: pipeline cũ im lặng bỏ."""
        self._generation += 1
        inp = self.gather(slot)
        local_text = build_local_briefing_text(inp)
        bubble = self._ctx.bubble
        if bubble is not None:
            bubble.show_message(local_text, mood="CHEER", timeout_ms=BRIEFING_BUBBLE_MS)
        since = email_since(slot == MIDDAY, previous_at, now or datetime.now().astimezone())
        coro = self.run_background(inp, local_text, generation=self._generation, email_from=since)
        try:
            spawn_background_task(coro, "work-briefing-upgrade")
        except RuntimeError:  # không có event loop (test đồng bộ)
            coro.close()
            logger.debug("Không có event loop, giữ briefing local")

    def _superseded(self, generation: int) -> bool:
        return generation != self._generation

    async def run_background(
        self, inp: BriefingInput, local_text: str, generation: Optional[int] = None,
        email_from: Optional[datetime] = None,
    ) -> None:
        """Email + Hermes (chung 1 hạn chót ~40s) → bubble → TTS đúng 1 lần với bản cuối, nếu còn phù hợp."""
        generation = self._generation if generation is None else generation
        run = _Run(text=local_text, shown=local_text, started=time.monotonic())
        try:
            await asyncio.wait_for(self._pipeline(inp, run, generation, email_from), PIPELINE_DEADLINE_SECS)
        except asyncio.TimeoutError:
            logger.info("Briefing nền quá %.0fs, giữ bản hiện có", PIPELINE_DEADLINE_SECS)
        if self._superseded(generation) or not self._manifest.settings.get("speak_briefing", True):
            return
        if speech_suppressed(self._ctx, self._calendar_repo) or not self._bubble_allows_speech(run):
            return
        try:
            await tts_service.speak(run.text)
        except Exception:
            logger.exception("Không đọc to được briefing")

    async def _pipeline(self, inp: BriefingInput, run: "_Run", generation: int, email_from: Optional[datetime]) -> None:
        client = self._client()
        if self._manifest.settings.get("email_digest_enabled", True) and client is not None:
            digest = await fetch_email_digest(self._manifest, client, inp.slot, since=email_from)
            if self._superseded(generation):
                return
            inp.apply_email_digest(digest, int(self._manifest.settings.get("email_max_items", 8)))
            run.text = build_local_briefing_text(inp)
            bubble = self._ctx.bubble
            if run.text != run.shown and bubble is not None and isValid(bubble) and bubble.current_text() == run.shown:
                bubble.update_text(run.text)
                run.shown = run.text
        hermes = await self._hermes_text(inp, run.shown, run.elapsed(), lambda: self._superseded(generation))
        run.text = hermes or run.text

    def _bubble_allows_speech(self, run: "_Run") -> bool:
        """Đọc nếu bubble đang hiện đúng bản cuối; hoặc đã tự ẩn mà chưa trễ quá ~15s. Bubble hiện tin khác / quá trễ → im."""
        bubble = self._ctx.bubble
        if bubble is None or not isValid(bubble):
            return True
        if bubble.is_busy():
            return bubble.current_text() == run.text
        return run.elapsed() <= LATE_RESULT_SECS

    async def _hermes_text(self, inp: BriefingInput, local_text: str, elapsed: float = 0.0, superseded=lambda: False) -> str:
        """Văn bản Hermes đã thay vào bubble; "" nếu giữ bản local (bubble đã đổi, hoặc kết quả đến quá trễ khi bubble đã ẩn)."""
        text, mood = await self._rewrite(inp)
        bubble = self._ctx.bubble
        if not text or bubble is None or not isValid(bubble) or superseded():
            return ""
        if not bubble.is_busy():  # bubble đã tự ẩn trong lúc chờ: chỉ hiện lại nếu chưa trễ quá ~15s
            if elapsed > LATE_RESULT_SECS:
                return ""
            bubble.show_message(text, mood=mood, timeout_ms=BRIEFING_BUBBLE_MS)
        elif bubble.current_text() == local_text:
            bubble.update_text(text, mood)
        else:  # bubble đang hiện tin khác → không đè
            return ""
        return text

    async def upgrade_with_hermes(self, inp: BriefingInput, local_text: str) -> bool:
        """True nếu bubble đã được thay bằng bản Hermes."""
        return bool(await self._hermes_text(inp, local_text))

    async def _rewrite(self, inp: BriefingInput) -> tuple[str, str]:
        """(text đã sạch, mood) từ Hermes; lỗi/không có client → ("", "CHEER")."""
        prompt = load_prompt(self._manifest, "briefing", briefing_prompt_values(inp))
        client = self._client()
        if not prompt or client is None:
            return "", "CHEER"
        try:
            raw = await asyncio.wait_for(
                client.complete_text([{"role": "user", "content": prompt}], timeout=HERMES_BRIEFING_TIMEOUT_SECS),
                HERMES_BRIEFING_TIMEOUT_SECS + 1,
            )
        except (HermesUnavailableError, HermesRequestRejectedError, asyncio.TimeoutError) as exc:
            logger.info("Briefing Hermes lỗi, giữ bản local: %s", exc)
            return "", "CHEER"
        match = MOOD_TAG_RE.match(raw)
        mood = match.group(1) if match else "CHEER"
        return sanitize_for_history(raw[match.end():] if match else raw).strip(), mood
