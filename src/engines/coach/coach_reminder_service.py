"""Nhắc agenda theo giờ (`when`) và mốc theo ngày — kiểm tra mỗi 60s, mỗi lần tối đa 1 bong bóng."""

import logging
from datetime import timedelta
from typing import Callable

from PySide6.QtCore import QObject, QTimer

from src.engines.coach.coach_agenda_and_milestone_reminder_timing import (
    agenda_reminder_key,
    agenda_text,
    due_agenda_reminders,
    due_milestone_reminders,
    milestone_text,
)
from src.engines.coach.coach_module_services import CoachModuleServices
from src.engines.coach.coach_review_prompt_gate import should_prompt
from src.engines.coach.coach_sync_plan_schemas import AgendaItem
from src.engines.coach.meeting_overlap_provider import in_meeting

logger = logging.getLogger("ted")
CHECK_INTERVAL_MS = 60_000
PRUNE_AFTER_DAYS = 2
BUBBLE_TIMEOUT_MS = 60_000


class CoachReminderService(QObject):
    def __init__(self, services: CoachModuleServices, launch: Callable[[AgendaItem], None], parent=None):
        super().__init__(parent)
        self._s, self._launch = services, launch
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check)
        self._stopped = False
        self._key = f"coach.{services.module_id}.reminded"

    def start(self) -> None:
        self._stopped = False
        self._timer.start(CHECK_INTERVAL_MS)

    def stop(self) -> None:
        self._stopped = True
        self._timer.stop()

    # ---- KV "đã nhắc": {key: ngày nhắc ISO}, xoá mục cũ hơn 2 ngày ----
    def _load(self) -> dict[str, str]:
        data = self._s.ctx.kv.get_json(self._key, {})
        return data if isinstance(data, dict) else {}

    def _remember(self, key: str) -> None:
        cutoff = (self._s.today() - timedelta(days=PRUNE_AFTER_DAYS)).isoformat()
        kept = {k: v for k, v in self._load().items() if v >= cutoff}
        kept[key] = self._s.today().isoformat()
        self._s.ctx.kv.set_json(self._key, kept)

    # ---- 1 lần kiểm tra ----
    def check(self) -> str:
        """Trả "agenda" | "milestone" | lý do bị chặn / "none" (để test và log)."""
        if self._stopped:
            return "stopped"
        now, state = self._s.now(), self._s.focus_state()
        allowed, reason = should_prompt(          # giống cổng ôn nhưng bỏ qua cap / "có câu đến hạn"
            now, state, self._s.policy(), attempts_today=0, due_count=1, new_available=1,
            snooze_until=self._s.snooze_until(), skip_date=self._s.skip_date(), in_meeting=in_meeting(self._s.db_engine, now, getattr(self._s.ctx, "registry", None)))
        if not allowed:
            return reason
        bubble = self._s.ctx.bubble
        if bubble is None or bubble.is_busy():
            return "bubble_busy"
        snapshot = self._s.plans.get_snapshot(self._s.module_id)
        if snapshot is None:
            return "none"
        reminded = self._load()
        # Kế hoạch cũ (chưa sync hôm nay) → không nhắc agenda của hôm qua; mốc theo ngày vẫn nhắc bình thường
        agenda_due = due_agenda_reminders(
            snapshot.agenda, now, self._s.plans.done_ids(self._s.module_id), reminded) if self._s.plan_is_today() else []
        if agenda_due:
            item = agenda_due[0]
            self._remember(agenda_reminder_key(now.date(), item.id))
            bubble.show_message(
                agenda_text(item), mood="GENTLE_NUDGE", timeout_ms=BUBBLE_TIMEOUT_MS,
                actions=[("Bắt đầu", lambda: None if self._stopped else self._launch(item)), ("Để sau", lambda: None)])
            return "agenda"
        milestones = due_milestone_reminders(snapshot.milestones, now, reminded)
        if milestones:
            milestone, days, key = milestones[0]
            self._remember(key)
            bubble.show_message(milestone_text(milestone, days), mood="GENTLE_NUDGE", timeout_ms=BUBBLE_TIMEOUT_MS)
            return "milestone"
        return "none"
