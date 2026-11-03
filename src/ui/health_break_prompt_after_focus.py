"""Gợi ý sức khỏe nhỏ NGAY SAU mỗi phiên Deep Work hoàn thành (ngoại lệ có chủ đích của "hạn chế hỏi").

Luồng: session_completed → chờ bubble chúc mừng tan → (không giữa Deep Work/họp; IDLE hoặc nghỉ tự động đều được / bubble rảnh / hộp Gỡ Rối đóng) →
hỏi Hermes (≤3s, chỉ profile Work) hoặc bảng offline → bubble 2 nút "Đã làm" / "Bỏ qua".
"Đã làm" → ghi DailyWellbeing (+bonus Health có trần), KHÔNG XP. Không giọng nói. Gọi từ main.py: `install_health_break_prompt(ctx, companion)`.
"""

import logging
import random
from datetime import datetime
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QObject, QTimer

from src.config import settings
from src.core.background_task_spawner import spawn_background_task
from src.core.focus_engine import FocusState
from src.core.gamification.health_break_contract_schema import HealthBreakSuggestion
from src.core.gamification.health_break_hermes_suggestion_fetcher import HealthBreakContext, fetch_hermes_suggestion
from src.core.gamification.health_break_rotation_state import HealthBreakRotationState
from src.core.gamification.health_break_suggestions import (
    WATER_DUE_MINUTES,
    pick_exercise_suggestion,
    pick_offline_suggestion,
)
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.i18n import i18n, tr

logger = logging.getLogger("ted")

SETTLE_DELAY_MS = 2500        # chờ câu chúc mừng/chime của phiên vừa xong tan trước khi hỏi
BUBBLE_TIMEOUT_MS = 25_000
ACK_TIMEOUT_MS = 3500

_PROMPTABLE_STATES = (FocusState.IDLE, FocusState.BREAK_RUNNING)

Route = Tuple[Optional[object], bool]   # (client Hermes work hoặc None, kid_safe)


class HealthBreakPromptController(QObject):
    def __init__(
        self, focus_engine, bubble, wellbeing: WellbeingDailyRepository, state: HealthBreakRotationState,
        resolve_route: Callable[[], Route],
        is_untangle_dialog_visible: Callable[[], bool] = lambda: False,
        health_stat_today: Callable[[], Optional[int]] = lambda: None,
        now_fn: Callable[[], datetime] = lambda: datetime.now().astimezone(),
        rng: Optional[random.Random] = None, settle_delay_ms: int = SETTLE_DELAY_MS, parent=None,
    ):
        super().__init__(parent)
        self._focus, self._bubble, self._wellbeing, self._state = focus_engine, bubble, wellbeing, state
        self._resolve_route, self._untangle_visible = resolve_route, is_untangle_dialog_visible
        self._health_stat_today, self._now, self._rng = health_stat_today, now_fn, rng or random.Random()
        self._settle_delay_ms = settle_delay_ms
        self._connected = False

    def connect_signals(self) -> None:
        if not self._connected:
            self._focus.session_completed.connect(self._on_session_completed)
            self._focus.meeting_completed.connect(self._on_meeting_completed)   # sau họp cũng gợi ý như sau Deep Work
            self._connected = True

    def disconnect_signals(self) -> None:
        if self._connected:
            self._focus.session_completed.disconnect(self._on_session_completed)
            self._focus.meeting_completed.disconnect(self._on_meeting_completed)
            self._connected = False

    def _on_session_completed(self, _title: str, actual_mins: int, _distractions: int) -> None:
        # session_completed chỉ phát khi stop_session(completed=True) (focus_rating=5); mins=0 = phiên rỗng
        if not settings.health_break_prompt_enabled or actual_mins <= 0:
            return
        QTimer.singleShot(self._settle_delay_ms,
                          lambda: spawn_background_task(self.offer(actual_mins), "health-break-offer"))

    def _on_meeting_completed(self, _kind: str, actual_mins: int) -> None:
        self._on_session_completed("", actual_mins, 0)

    def _blocked(self) -> bool:
        """Không hỏi khi đang Deep Work/tạm dừng/họp, bubble bận, hộp Gỡ Rối mở hoặc đã tắt trong Settings.
        Cho phép IDLE và BREAK_RUNNING (quãng nghỉ tự động sau phiên chính là lúc hợp lý nhất để gợi ý)."""
        return (not settings.health_break_prompt_enabled or self._focus.state not in _PROMPTABLE_STATES
                or self._bubble.is_busy() or self._untangle_visible())

    def _build_context(self, session_minutes: int, now: datetime) -> HealthBreakContext:
        today = self._wellbeing.get(now.date())
        return HealthBreakContext(
            session_minutes=session_minutes, breaks_today=today.breaks_taken, micro_done_today=today.micro_breaks_done,
            minutes_since_water=self._state.minutes_since_water(now), minutes_since_move=self._state.minutes_since_move(now),
            local_hour=now.hour, health_stat=self._health_stat_today(), recent_kinds=tuple(self._state.recent_kinds()),
            language=i18n.current_language)

    async def offer(self, session_minutes: int) -> bool:
        """Trả True nếu đã hiện bubble. Không raise (tính năng phụ, không được làm hỏng luồng focus)."""
        try:
            if self._blocked():
                return False
            now = self._now()
            ctx = self._build_context(session_minutes, now)
            client, kid_safe = self._resolve_route()
            suggestion = await fetch_hermes_suggestion(client, ctx) if client is not None else None
            is_exercise = False
            today_exercises = self._state.exercise_count_today(now)
            target = getattr(settings, "exercise_daily_target", 4)
            exercise_enabled = getattr(settings, "exercise_reminder_enabled", True)

            if suggestion is None:
                # Nếu nước đến hạn (>90p), ưu tiên nhắc nước; nếu không và chưa đạt mục tiêu 3-4 lần thể dục/ngày -> gợi ý thể dục
                water_due = (ctx.minutes_since_water is None or ctx.minutes_since_water > WATER_DUE_MINUTES) \
                    and not (ctx.recent_kinds and ctx.recent_kinds[-1] == "water")
                if not water_due and exercise_enabled and today_exercises < target:
                    suggestion = pick_exercise_suggestion(self._state.recent_action_ids(), now.hour, kid_safe, self._rng)
                    is_exercise = True
                else:
                    suggestion = pick_offline_suggestion(ctx.recent_kinds, ctx.minutes_since_water, now.hour, kid_safe, self._rng)

            if self._blocked():   # trong lúc chờ Hermes user có thể đã bắt đầu phiên mới
                return False
            self._show(suggestion, is_exercise=is_exercise, current_count=today_exercises, target_count=target)
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Không hiện được gợi ý sức khỏe sau Deep Work")
            return False

    def _show(
        self,
        suggestion: HealthBreakSuggestion,
        is_exercise: bool = False,
        current_count: int = 0,
        target_count: int = 4,
    ) -> None:
        self._state.record_shown(suggestion.kind)   # bỏ qua cũng tính là đã gợi ý → lần sau đổi loại
        self._state.record_shown_action(suggestion.action_id)
        self._focus.set_mood("REST")

        if is_exercise:
            header = tr("exercise_prompt_header", current=current_count + 1, target=target_count)
            text = f"{header}\n{suggestion.text_for(i18n.current_language)}"
            actions = [
                (tr("exercise_action_done"), lambda: self.mark_done(suggestion.kind, is_exercise=True)),
                (tr("health_break_action_skip"), lambda: None),
                (tr("exercise_action_switch"), lambda: self.switch_exercise()),
            ]
        else:
            text = suggestion.text_for(i18n.current_language)
            actions = [
                (tr("health_break_action_done"), lambda: self.mark_done(suggestion.kind, is_exercise=False)),
                (tr("health_break_action_skip"), lambda: None),
            ]

        self._bubble.show_message(
            text, mood="REST", timeout_ms=BUBBLE_TIMEOUT_MS, actions=actions
        )

    def switch_exercise(self) -> None:
        """Đổi sang một bài tập thể dục tại chỗ khác (chống đẩy, kéo xà, gập lưng, squats...)."""
        try:
            now = self._now()
            _client, kid_safe = self._resolve_route()
            suggestion = pick_exercise_suggestion(self._state.recent_action_ids(), now.hour, kid_safe, self._rng)
            today_exercises = self._state.exercise_count_today(now)
            target = getattr(settings, "exercise_daily_target", 4)
            self._show(suggestion, is_exercise=True, current_count=today_exercises, target_count=target)
        except Exception:  # noqa: BLE001
            logger.exception("Không thể đổi bài tập thể dục")

    def mark_done(self, kind: str, is_exercise: bool = False) -> None:
        try:
            now = self._now()
            self._wellbeing.log_micro_break(now.date(), kind)
            self._state.record_done(kind, now)
            if is_exercise:
                new_count = self._state.record_exercise_done(now)
                target = getattr(settings, "exercise_daily_target", 4)
                if new_count >= target:
                    ack_msg = tr("exercise_done_cheer", target=target)
                else:
                    ack_msg = tr("exercise_done_progress", current=new_count, target=target)
            else:
                ack_msg = tr("health_break_done_ack")
        except Exception:  # noqa: BLE001
            logger.exception("Không ghi được hành động sức khỏe nhỏ")
            return
        self._bubble.show_message(ack_msg, mood="CHEER", timeout_ms=ACK_TIMEOUT_MS)


def _make_route_resolver(ctx) -> Callable[[], Route]:
    """Profile Work → client Hermes của module đó; coach/khác → offline bản an toàn cho trẻ (không gọi Hermes)."""
    def resolve() -> Route:
        active = ctx.registry.active()
        module_id, engine = (active.id, active.engine) if active else ("work", "work")
        if engine != "work":
            return None, True
        return ctx.client_pool.for_module(module_id), False
    return resolve


def _make_health_stat_reader(db_engine, wellbeing: WellbeingDailyRepository) -> Callable[[], Optional[int]]:
    def read() -> Optional[int]:
        try:
            from src.core.gamification.day_signals_collector import collect_day_signals
            from src.core.gamification.wellbeing_stat_formulas import compute_day_stats
            from src.core.gamification.xp_ledger_repository import XpLedgerRepository
            day = datetime.now().astimezone().date()
            return compute_day_stats(collect_day_signals(db_engine, XpLedgerRepository(db_engine), wellbeing, day)).health
        except Exception:  # noqa: BLE001 - thiếu chỉ số chỉ làm ngữ cảnh nghèo đi
            logger.warning("Không đọc được chỉ số Health cho gợi ý sức khỏe", exc_info=True)
            return None
    return read


def install_health_break_prompt(ctx, companion) -> HealthBreakPromptController:
    """Caller (main.py) PHẢI giữ tham chiếu; controller là con của `companion` nên không bị GC."""
    from src.core.models import db
    wellbeing = WellbeingDailyRepository(db.engine)

    def untangle_visible() -> bool:
        dialog = getattr(companion, "untangle_dialog", None)
        return bool(dialog is not None and dialog.isVisible())

    controller = HealthBreakPromptController(
        ctx.focus_engine, ctx.bubble, wellbeing, HealthBreakRotationState(ctx.kv), _make_route_resolver(ctx),
        is_untangle_dialog_visible=untangle_visible,
        health_stat_today=_make_health_stat_reader(db.engine, wellbeing), parent=companion)
    controller.connect_signals()
    return controller
