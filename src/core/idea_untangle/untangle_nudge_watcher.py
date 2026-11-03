"""Watcher gợi ý Gỡ Rối: lắng nghe FocusEngine, tính ngưỡng 1 lần/phiên, đánh giá mỗi 5 phút, tôn trọng cooldown.

Không import UI: UI tiêm `on_offer`, `is_suppressed`; hành động "Kể Ted nghe" gọi `open_offer()` →
phát `nudge_requested(module_id, task_id, kind, trigger)` để phase 06 mở hộp thoại.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QObject, Signal
from sqlalchemy.engine import Engine
from sqlmodel import Session

from src.config import settings
from src.core.app_state_key_value_store import KeyValueStore
from src.core.focus_engine import FocusState
from src.core.idea_untangle import focus_history_baseline_queries as history
from src.core.idea_untangle.untangle_adaptive_trigger_rules import (
    NudgeState, Snapshot, Thresholds, compute_thresholds, cooldown_allows,
    evaluate_untangle_trigger, record_accepted, record_shown,
)
from src.core.idea_untangle.untangle_coach_stuck_signals import CoachSignals, coach_signals
from src.core.idea_untangle.untangle_problem_kinds_by_engine import DEFAULT_KIND, normalize_kind
from src.core.models import Task

logger = logging.getLogger("ted")

NUDGE_KV_KEY = "idea_untangle_nudge_v2"
CHECK_EVERY_SECS = 300


@dataclass(frozen=True)
class NudgeOffer:
    reason: str
    module_id: str
    task_id: str
    task_title: str
    kind: str


class UntangleNudgeWatcher(QObject):
    nudge_requested = Signal(str, str, str, str)    # (module_id, task_id, kind, trigger)

    def __init__(
        self,
        focus_engine,
        db_engine: Engine,
        kv: KeyValueStore,
        module_context: Callable[[], Tuple[str, str]],      # → (module_id, engine "work"|"coach")
        on_offer: Callable[[NudgeOffer], None],
        is_suppressed: Callable[[], bool] = lambda: False,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._focus, self._db, self._kv = focus_engine, db_engine, kv
        self._module_context, self._on_offer, self._is_suppressed, self._now = module_context, on_offer, is_suppressed, now_fn
        self._connected = False
        self._thresholds = Thresholds()
        self._consecutive = 0
        self._focus_mins_before = 0.0
        self._estimated_mins = 0.0
        self._last_offer: Optional[NudgeOffer] = None

    # ---- kết nối (idempotent) ----
    def connect_signals(self) -> None:
        if not self._connected:
            self._focus.session_started.connect(self._on_session_started)
            self._focus.timer_tick.connect(self._on_tick)
            self._connected = True

    def disconnect_signals(self) -> None:
        if self._connected:
            self._focus.session_started.disconnect(self._on_session_started)
            self._focus.timer_tick.disconnect(self._on_tick)
            self._connected = False

    # ---- baseline: 1 lần mỗi phiên mới, lỗi DB chỉ log ----
    def _on_session_started(self, task_id: str, _title: str) -> None:
        try:
            self._thresholds = compute_thresholds(
                history.historical_overrun_ratios(self._db), history.daily_same_task_session_counts(self._db),
                history.distraction_rate_baseline(self._db))
            self._consecutive = history.consecutive_sessions_on_task_today(self._db, task_id) if task_id else 0
            self._focus_mins_before = float(history.task_focus_minutes_total(self._db, task_id)) if task_id else 0.0
            self._estimated_mins = 0.0
            if task_id:
                with Session(self._db) as s:
                    task = s.get(Task, task_id)
                    if task:
                        self._estimated_mins = max(1, task.estimated_pomodoros) * max(1, int(settings.default_pomodoro_mins))
        except Exception:
            logger.exception("Untangle nudge: không tính được baseline, dùng mặc định")
            self._thresholds, self._consecutive, self._focus_mins_before, self._estimated_mins = Thresholds(), 0, 0.0, 0.0

    def _on_tick(self, _remaining: int, _total: int, _title: str) -> None:
        elapsed = int(self._focus.elapsed_seconds)
        if elapsed > 0 and elapsed % CHECK_EVERY_SECS == 0:
            self.check(elapsed)

    # ---- đánh giá (public để test) ----
    def check(self, elapsed: int) -> Optional[NudgeOffer]:
        """Không bao giờ ném lỗi vào tick."""
        try:
            return self._check(elapsed)
        except Exception:
            logger.exception("Untangle nudge: lỗi khi đánh giá, bỏ qua tick")
            return None

    def _check(self, elapsed: int) -> Optional[NudgeOffer]:
        if not settings.untangle_nudge_enabled or self._focus.state != FocusState.DEEP_WORK_RUNNING:
            return None
        module_id, engine_name = self._module_context()
        now = self._now()
        coach = coach_signals(self._db, module_id, now) if engine_name == "coach" else CoachSignals()
        snap = Snapshot(
            running_deep_work=True, elapsed_secs=elapsed, task_focus_mins_before=self._focus_mins_before,
            estimated_mins=self._estimated_mins, consecutive_sessions=self._consecutive,
            distraction_count=int(self._focus.distraction_count), coach_wrong_streak=coach.wrong_streak)
        reason = evaluate_untangle_trigger(snap, self._thresholds)
        if reason is None:
            return None
        task_id = self._focus.active_task_id or ""
        key = task_id or f"session:{module_id}"
        state = NudgeState.from_json(self._kv.get_json(NUDGE_KV_KEY))
        if not cooldown_allows(state, key, now) or self._is_suppressed():
            return None
        kind = normalize_kind(engine_name, coach.kind if engine_name == "coach" else DEFAULT_KIND)
        offer = NudgeOffer(reason, module_id, task_id, self._focus.active_task_title, kind)
        self._kv.set_json(NUDGE_KV_KEY, record_shown(state, key, now).to_json())   # ghi TRƯỚC khi hiện: lỗi UI cũng không spam
        self._last_offer = offer
        self._on_offer(offer)
        return offer

    # ---- kết quả người dùng ----
    def open_offer(self) -> None:
        """Gọi từ nút "🧶 Kể Ted nghe": reset backoff + phát tín hiệu cho phase 06 mở hộp thoại."""
        offer = self._last_offer
        if offer is None:
            return
        try:
            self._kv.set_json(NUDGE_KV_KEY, record_accepted(NudgeState.from_json(self._kv.get_json(NUDGE_KV_KEY))).to_json())
        except Exception:
            logger.exception("Untangle nudge: không lưu được trạng thái accepted")
        self.nudge_requested.emit(offer.module_id, offer.task_id, offer.kind, offer.reason)
