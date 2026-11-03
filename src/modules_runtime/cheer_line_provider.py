"""Câu động viên khi click đơn lên pet: pool local (cheers.md của module work) + 1/5 lần xin Hermes 1 câu mới,
kèm việc đang làm + việc Khẩn cấp & Quan trọng (Q1)."""

import asyncio
import logging
import random
import re
from typing import Optional

from PySide6.QtCore import QTimer

from src.bridge.hermes_client import HermesRequestRejectedError, HermesUnavailableError, sanitize_for_history
from src.core.focus_engine import FocusState
from src.modules_runtime.module_manifest_schema import ModuleManifest
from src.modules_runtime.prompt_template_renderer import load_prompt, parse_bullet_lines

logger = logging.getLogger("ted")

HERMES_CHEER_TIMEOUT_SECS = 4.0
HERMES_CHEER_CHANCE = 0.2
CHEER_MOOD_MILLIS = 4000
SUMMARY_BUBBLE_MILLIS = 12_000  # có danh sách việc → giữ bubble lâu hơn để kịp đọc / bấm link task
PERSONA_CATCHPHRASE_CHANCE = 0.5
COACH_CHEER_PROMPT = "Động viên mình 1 câu ngắn"
# Dùng khi thiếu hẳn module work / file cheers.md
BUILTIN_CHEERS = ["Ted ở đây rồi nè, làm tiếp thôi nào!", "Bạn đỉnh thật sự, Ted nói thiệt đó!"]
_MOOD_TAG = re.compile(r"\[MOOD:[A-Z_]+\]")


class CheerLineProvider:
    def __init__(self, registry, pool, focus_engine=None, bubble=None, rng: Optional[random.Random] = None,
                 task_db=None):
        self._task_db = task_db  # None → db toàn cục (nạp lười lúc click)
        self._registry = registry
        self._pool = pool
        self._focus = focus_engine
        self._bubble = bubble
        self._rng = rng or random.Random()

    def pick_local(self, manifest: Optional[ModuleManifest]) -> str:
        """Module có prompts.cheers dùng pool riêng; module khác (coach) mượn pool của module work.
        Nhân vật đã cấu hình tính cách (click 5 lần lên pet) → nửa số lần nói câu cửa miệng của tính cách đó;
        nhân vật Character Pack còn trộn thêm câu thoại theo mood hiện tại (expressions trong characters.json)."""
        from src.core.character_pack_loader import MOOD_TO_STATE
        from src.core.character_persona_profiles import saved_persona
        persona = saved_persona()
        if persona is not None and self._rng.random() < PERSONA_CATCHPHRASE_CHANCE:
            mood = getattr(self._focus, "current_mood", "IDLE") if self._focus is not None else "IDLE"
            lines = persona.catchphrases() + persona.mood_lines(MOOD_TO_STATE.get(mood, "idle"))
            return self._rng.choice(lines)
        for source in (manifest, self._registry.get("work")):
            if source is None:
                continue
            path = source.prompt_path("cheers")
            if path is None:
                continue
            try:
                lines = parse_bullet_lines(path.read_text(encoding="utf-8"))
            except OSError as exc:
                logger.warning("Không đọc được %s: %s", path, exc)
                continue
            if lines:
                return self._rng.choice(lines)
        return self._rng.choice(BUILTIN_CHEERS)

    def should_ask_hermes(self, manifest: Optional[ModuleManifest]) -> bool:
        """Gate: 1/5 cơ hội, không phải lúc Deep Work, và module có kết nối khả dụng."""
        if manifest is None or self._pool.for_module(manifest.id) is None:
            return False
        if self._focus is not None and self._focus.state in (FocusState.DEEP_WORK_RUNNING, FocusState.PAUSED, FocusState.MEETING_RUNNING):
            return False
        return self._rng.random() < HERMES_CHEER_CHANCE

    async def cheer_text(self, manifest: Optional[ModuleManifest]) -> str:
        if self.should_ask_hermes(manifest):
            text = await self._ask_hermes(manifest)
            if text:
                return text
        return self.pick_local(manifest)

    async def _ask_hermes(self, manifest: ModuleManifest) -> str:
        if manifest.engine == "work":
            ctx = self._focus.get_context_snapshot() if self._focus else {}
            prompt = load_prompt(manifest, "cheer", {"state": ctx.get("status", ""), "task": ctx.get("task", "")})
        else:
            prompt = COACH_CHEER_PROMPT
        if not prompt:
            return ""
        client = self._pool.for_module(manifest.id)
        try:
            raw = await asyncio.wait_for(
                client.complete_text([{"role": "user", "content": prompt}], timeout=HERMES_CHEER_TIMEOUT_SECS),
                HERMES_CHEER_TIMEOUT_SECS + 1,
            )
        except (HermesUnavailableError, HermesRequestRejectedError, asyncio.TimeoutError):
            return ""
        return sanitize_for_history(_MOOD_TAG.sub("", raw)).strip()

    def task_summary(self) -> tuple[str, list[tuple[str, str]]]:
        """Việc đang làm + việc Q1 (Khẩn cấp & Quan trọng); lỗi DB → bỏ qua, chỉ còn câu động viên."""
        from src.engines.work.pet_click_task_status_summary import build_task_status_summary
        try:
            if self._task_db is None:
                from src.core.models import db
                self._task_db = db
            return build_task_status_summary(self._task_db, self._focus)
        except Exception:
            logger.exception("Không lấy được tóm tắt task khi click pet")
            return "", []

    async def show_cheer(self):
        """Hiện bubble động viên kèm việc đang làm + việc Q1, mood CHEER 4s rồi trả về mood cũ."""
        text = await self.cheer_text(self._registry.active())
        summary, task_links = self.task_summary()
        if self._bubble is not None and not self._bubble.has_pending_actions():
            if summary:
                self._bubble.show_message(f"{text}\n\n{summary}", mood="CHEER",
                                          timeout_ms=SUMMARY_BUBBLE_MILLIS, task_links=task_links)
            else:
                self._bubble.show_message(text, mood="CHEER")
        if self._focus is not None:
            previous = self._focus.current_mood
            self._focus.set_mood("CHEER")
            QTimer.singleShot(CHEER_MOOD_MILLIS, lambda: self._restore_mood(previous))

    async def show_cheer_in_chat(self):
        """Click đơn mở bubble chat → câu động viên + việc đang làm/Q1 thành dòng đầu của Ted trong khung chat."""
        text = await self.cheer_text(self._registry.active())
        summary, _ = self.task_summary()
        if self._bubble is not None:
            self._bubble.append_ted_line(f"{text}\n\n{summary}" if summary else text)

    def _restore_mood(self, previous: str):
        # Chỉ trả mood nếu chưa có gì khác đổi mood trong 4s (vd phiên focus vừa bắt đầu)
        if self._focus is not None and self._focus.current_mood == "CHEER":
            self._focus.set_mood(previous)
