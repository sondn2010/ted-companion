"""Bộ hẹn giờ nhắc ôn: tick theo policy.review_interval_mins + khi bắt đầu nghỉ giải lao → cổng → bong bóng → popup."""

import logging
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer

from src.core.focus_engine import FocusState
from src.engines.coach.coach_module_services import CoachModuleServices
from src.engines.coach.coach_prompt_round_robin_arbiter import SHARED_ARBITER, RoundRobinArbiter
from src.engines.coach.coach_review_prompt_gate import should_prompt
from src.engines.coach.coach_review_session_builder import REVIEW_SCHEDULER_LIMIT
from src.engines.coach.meeting_overlap_provider import in_meeting

logger = logging.getLogger("ted")
SNOOZE_MINS = 10
BUBBLE_TIMEOUT_MS = 45_000


class CoachReviewScheduler(QObject):
    def __init__(
        self, services: CoachModuleServices, start_review: Callable[[int], None],
        refill: Callable[[], None] = lambda: None, arbiter: RoundRobinArbiter = SHARED_ARBITER, parent=None,
    ):
        super().__init__(parent)
        self._s, self._start_review, self._refill, self._arbiter = services, start_review, refill, arbiter
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._interval_mins: Optional[int] = None
        self._stopped = False
        self._retry_pending = False

    # ---- vòng đời ----
    def start(self) -> None:
        self._stopped = False
        self._rearm()
        self._s.ctx.focus_engine.state_changed.connect(self._on_state_changed)

    def stop(self) -> None:
        self._stopped = True
        self._interval_mins = None   # lần start sau phải đặt lại timer
        self._timer.stop()
        self._arbiter.forget(self._s.module_id)
        try:
            self._s.ctx.focus_engine.state_changed.disconnect(self._on_state_changed)
        except (RuntimeError, TypeError):
            pass   # chưa connect / đã ngắt

    def rearm(self) -> None:
        self._rearm()

    def _rearm(self) -> None:
        """Đặt lại timer khi policy.review_interval_mins đổi (sau mỗi lần sync). Đã stop → không làm gì."""
        if self._stopped:
            return
        mins = self._s.policy().review_interval_mins
        if mins != self._interval_mins:
            self._interval_mins = mins
            self._timer.start(mins * 60_000)

    def _on_state_changed(self, state: str, _mood: str) -> None:
        if state == FocusState.BREAK_RUNNING:
            self.tick()

    # ---- 1 lần kiểm tra ----
    def tick(self) -> str:
        """Trả lý do (để test/log). Mỗi tick cũng bổ sung câu hỏi ở nền, trừ khi đang DEEP_WORK."""
        if self._stopped:
            return "stopped"
        self._rearm()
        state = self._s.focus_state()
        if state != FocusState.DEEP_WORK_RUNNING:
            self._refill()
        now, policy = self._s.now(), self._s.policy()
        due = self._s.items.due_count(self._s.module_id, now)
        allowed, reason = should_prompt(
            now, state, policy, attempts_today=self._s.attempts_today(), due_count=due,
            new_available=self._s.new_available(policy), snooze_until=self._s.snooze_until(),
            skip_date=self._s.skip_date(), in_meeting=in_meeting(self._s.db_engine, now, getattr(self._s.ctx, "registry", None)))
        if not allowed:
            self._arbiter.forget(self._s.module_id)   # hết đủ điều kiện → không chặn module khác
            return reason
        bubble = self._s.ctx.bubble
        if bubble is None or bubble.is_busy() or not self._arbiter.may_prompt(self._s.module_id, now):
            self._arbiter.mark_waiting(self._s.module_id, now)   # lượt sau module này được ưu tiên (Red Team #11)
            self._schedule_retry()
            return "bubble_busy"
        self._arbiter.record_prompt(self._s.module_id, now)
        count = due or self._s.new_available(policy)
        bubble.show_message(
            f"Có {count} câu ôn nè 🧠", mood="GENTLE_NUDGE", timeout_ms=BUBBLE_TIMEOUT_MS,
            actions=[("Làm", self._guarded(lambda: self._start_review(REVIEW_SCHEDULER_LIMIT))),
                     (f"{SNOOZE_MINS}' nữa", self._guarded(lambda: self._s.snooze(SNOOZE_MINS))),
                     ("Bỏ qua hôm nay", self._guarded(self._s.skip_today))])
        return "prompted"

    def _guarded(self, fn: Callable[[], None]) -> Callable[[], None]:
        """Nút bong bóng của engine đã stop (module tắt) → bỏ qua."""
        return lambda: None if self._stopped else fn()

    def _schedule_retry(self) -> None:
        """Bị chặn vì bong bóng bận → thử lại 1 lần ngay sau khi bong bóng hết hạn (interval dài không bị lỡ lượt)."""
        if self._retry_pending:
            return
        self._retry_pending = True
        QTimer.singleShot(BUBBLE_TIMEOUT_MS + 1000, self._retry_tick)

    def _retry_tick(self) -> None:
        self._retry_pending = False
        if not self._stopped:
            self.tick()
