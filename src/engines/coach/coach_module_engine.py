"""Engine module `coach`: scheduler ôn tập, nhắc agenda/mốc, gửi báo cáo tiến độ, tab Hôm nay + Tiến độ & mốc.
Giống nhau cho con và bố; mọi khác biệt nằm ở manifest + profile Hermes. Sync/onboarding ([TED_SYNC_PLAN],
[TED_ONBOARDING]) chạy qua CoachSyncService; `sync_handler` là điểm kích hoạt thủ công (menu, nút 🔄)."""

import logging
from typing import Callable, Optional

from PySide6.QtCore import QTimer
from shiboken6 import isValid

from src.core.background_task_spawner import spawn_background_task
from src.core.models import db
from src.engines.coach.agenda_kind_launcher import AgendaKindLauncher
from src.engines.coach.busy_slots_provider import collect_busy_slots
from src.engines.coach.coach_onboarding_prompt import CoachOnboardingPrompt
from src.engines.coach.coach_module_services import CoachModuleServices
from src.engines.coach.coach_reminder_service import CoachReminderService
from src.engines.coach.coach_review_scheduler import CoachReviewScheduler
from src.engines.coach.coach_review_session_builder import REVIEW_NOW_LIMIT
from src.engines.coach.coach_sync_service import CoachSyncService
from src.engines.coach.progress_outbox_sender import ProgressOutboxSender
from src.modules_runtime.module_engine_base_and_factory import ModuleEngineBase

logger = logging.getLogger("ted")
OUTBOX_INTERVAL_MS = 60 * 60 * 1000
FIRST_SYNC_DELAY_MS = 3_000          # mở app → đợi UI ổn định rồi mới sync đầu ngày
DAY_ROLLOVER_CHECK_MS = 60 * 60 * 1000


class CoachModuleEngine(ModuleEngineBase):
    def __init__(self, manifest, ctx, db_engine=None, services: Optional[CoachModuleServices] = None):
        super().__init__(manifest, ctx)
        self.services = services or CoachModuleServices(manifest, ctx, db_engine if db_engine is not None else db.engine)
        self.services.on_changed = self._refresh_tab
        self.services.request_sync = self._request_sync
        self.sync_handler: Optional[Callable[[], None]] = lambda: self._spawn_sync(manual=True)  # menu + nút 🔄
        self.launcher = AgendaKindLauncher(self.services)
        self.scheduler = CoachReviewScheduler(
            self.services,
            start_review=lambda limit: self.launcher.start_quiz_session(limit, respect_new_cap=True),
            refill=self.launcher.refill_in_background)
        self.reminders = CoachReminderService(self.services, self.launcher.launch)
        self._stopped = False
        self._tasks: set = set()   # sync/outbox đang chạy: stop() huỷ hết (L1)
        self.onboarding = CoachOnboardingPrompt(self.services)
        self.services.start_onboarding = self.onboarding.start
        self.sync_service = CoachSyncService(
            self.services,
            busy_slots=lambda: collect_busy_slots(getattr(ctx, "registry", None), self.services.db_engine, self.services.now(), self.services.tz),
            on_needs_onboarding=self.onboarding.offer, on_plan_applied=self.scheduler.rearm)
        self.outbox_sender = ProgressOutboxSender(self.services, lambda: self._spawn_sync(manual=False))
        self._outbox_timer = QTimer()
        self._outbox_timer.timeout.connect(self.run_outbox_cycle)
        self._first_sync_timer = QTimer()
        self._first_sync_timer.setSingleShot(True)
        self._first_sync_timer.timeout.connect(self.maybe_daily_sync)
        self._rollover_timer = QTimer()
        self._rollover_timer.timeout.connect(self.maybe_daily_sync)
        self._tab = None
        self._actions = {
            "today": self._open_today, "review_now": self._review_now, "ask": self._open_ask,
            "progress": self._open_progress, "sync": self._sync_action,
        }

    # ---- vòng đời ----
    def start(self) -> None:
        self._stopped = False
        self.scheduler.start()
        self.reminders.start()
        self._outbox_timer.start(OUTBOX_INTERVAL_MS)
        self._first_sync_timer.start(FIRST_SYNC_DELAY_MS)   # cũng là "module vừa được bật"
        self._rollover_timer.start(DAY_ROLLOVER_CHECK_MS)
        self._set_reply_json_handler(self._on_reply_json)
        self.run_outbox_cycle()

    def stop(self) -> None:
        """Tắt module: dừng timer, huỷ sync/outbox đang bay, chặn mọi callback muộn (rearm/offer/bong bóng)."""
        self._stopped = True
        self.sync_service.stop()
        self.onboarding.stop()
        self.scheduler.stop()
        self.reminders.stop()
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
        for timer in (self._outbox_timer, self._first_sync_timer, self._rollover_timer):
            timer.stop()
        self._set_reply_json_handler(None)

    def run_outbox_cycle(self) -> None:
        coro = self.outbox_sender.run_cycle()
        self._spawn(coro, f"coach-outbox-{self.manifest.id}")

    # ---- sync / onboarding ----
    def _request_sync(self) -> None:
        if self.sync_handler is not None:
            self.sync_handler()

    def _sync_action(self) -> None:
        self._request_sync()

    def _spawn_sync(self, manual: bool) -> None:
        """Sync ở nền (qasync). `manual`=True → có bong bóng báo kết quả; tự động thì im lặng."""
        self._spawn(self.sync_service.sync(manual=manual), f"coach-sync-{self.manifest.id}")

    def _spawn(self, coro, name: str) -> None:
        """Chạy nền + theo dõi để stop() huỷ được; đã stop thì không chạy."""
        if self._stopped:
            coro.close()
            return
        try:
            task = spawn_background_task(coro, name)
        except RuntimeError:   # chưa có event loop
            coro.close()
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def maybe_daily_sync(self) -> None:
        """Mở app / qua ngày mới (local) mà chưa sync thành công hôm nay → sync im lặng."""
        if self.sync_service.is_due_today():
            self._spawn_sync(manual=False)

    def _set_reply_json_handler(self, handler: Optional[Callable[[dict], None]]) -> None:
        register = getattr(self.ctx.quick_chat, "set_reply_json_handler", None)
        if register is not None:
            register(self.manifest.id, handler)

    def _on_reply_json(self, data: dict) -> None:
        """Khối <json> cuối câu trả lời chat: {"onboarding":"done"} → xoá cờ + sync lại ngay."""
        if self._stopped or data.get("onboarding") != "done" or data.get("learner") not in (None, self.services.learner_id):
            return
        if not self.services.needs_onboarding():   # chỉ xử lý khi thật sự đang onboarding (khối <json> lạc/giả bị bỏ qua)
            return
        self.services.set_needs_onboarding(False)
        self._spawn_sync(manual=True)

    # ---- menu ----
    def handle_action(self, action_id: str) -> None:
        handler = self._actions.get(action_id)
        if handler is None:
            logger.warning("Coach engine không có action '%s'", action_id)
            return
        handler()

    def _review_now(self) -> None:
        """Người dùng chủ động: bỏ qua cap/khung giờ, tối đa 20 câu."""
        self.launcher.start_quiz_session(REVIEW_NOW_LIMIT)

    def _open_ask(self) -> None:
        self.ctx.quick_chat.open_for(self.manifest.id)

    def _open_today(self) -> None:
        self._show_tab(lambda tab: tab.show_today())

    def _open_progress(self) -> None:
        self._show_tab(lambda tab: tab.show_progress())

    def _show_tab(self, select: Callable) -> None:
        dashboard = self.ctx.dashboard
        if dashboard is None:
            return
        if self._tab is not None and isValid(self._tab):
            select(self._tab)
            dashboard.tabs.setCurrentWidget(self._tab)
        dashboard.show()
        dashboard.raise_()
        dashboard.activateWindow()

    # ---- tab ----
    def build_dashboard_tab(self):
        from src.ui.module_tabs.coach_module_tab_widget import CoachModuleTabWidget

        self._tab = CoachModuleTabWidget(self.services, self.launcher)  # mới mỗi lần: tab cũ bị deleteLater
        return self._tab

    def _refresh_tab(self) -> None:
        """Gọi từ mọi nơi dữ liệu đổi (kể cả coroutine nền) → luôn kiểm tra widget còn sống (Red Team #3)."""
        if self._tab is not None and isValid(self._tab):
            self._tab.refresh()

