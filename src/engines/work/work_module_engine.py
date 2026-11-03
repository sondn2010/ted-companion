"""Engine module `work`: briefing đầu ngày, hỏi Ted (KB), Rocks, lịch (kéo từ Hermes → cache → nhắc họp offline)."""

import logging
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import QTimer
from shiboken6 import isValid

from src.core.background_task_spawner import spawn_background_task
from src.core.models import db
from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventRepository, event_end
from src.engines.work.calendar_sync_service import CalendarSyncService
from src.engines.work.daily_briefing_builder import sanitize_untrusted_text
from src.engines.work.meeting_reminder_service import MeetingReminderService
from src.engines.work.rock_memory_sync import format_rock_update, send_rock_update
from src.engines.work.rock_model_and_repository import Rock, RockRepository, rock_age_days
from src.engines.work.work_briefing_due_window import MIDDAY, slot_for_time
from src.engines.work.work_briefing_flow import WorkBriefingFlow, today_calendar_events
from src.engines.work.work_briefing_run_guard import mark_briefing_fired, read_last_briefing_at
from src.engines.work.work_focus_engine_signal_wiring import WorkFocusEngineSignalWiring
from src.engines.work.work_scheduled_briefing_timer import ScheduledBriefingTimer
from src.modules_runtime.module_engine_base_and_factory import ModuleEngineBase

logger = logging.getLogger("ted")
LAST_BRIEFING_KEY = "work.last_briefing_date"
LAST_MIDDAY_BRIEFING_KEY = "work.last_midday_briefing_date"
FIRST_POLL_DELAY_MS = 5_000


class WorkModuleEngine(ModuleEngineBase):
    def __init__(self, manifest, ctx, db_engine=None):
        super().__init__(manifest, ctx)
        self.db_engine = db_engine if db_engine is not None else db.engine
        self.rocks = RockRepository(self.db_engine)
        self.calendar_repo = CalendarEventRepository(self.db_engine)
        self._briefing = WorkBriefingFlow(manifest, ctx, self.db_engine, self.rocks, self.calendar_repo)
        self._clock = lambda: datetime.now().astimezone()  # test ghi đè để cố định giờ
        self._scheduled_briefing = ScheduledBriefingTimer(
            manifest.settings, self._last_briefing_dates, self.show_briefing, lambda: self._clock(),
            lambda: read_last_briefing_at(self.ctx.kv),
        )
        self._focus_wiring = WorkFocusEngineSignalWiring(manifest, ctx, self.db_engine, self.calendar_repo)
        self.calendar_sync = CalendarSyncService(manifest, ctx, self.calendar_repo)
        self._reminders: Optional[MeetingReminderService] = None
        self._first_poll: Optional[QTimer] = None
        self._poll_timer: Optional[QTimer] = None
        self._tab = None
        self._actions = {
            "briefing": self.show_briefing,
            "tasks": self._open_tasks_list,
            "ask": self._open_ask,
            "rocks": self._open_rocks_tab,
            "calendar": self._show_calendar,
        }

    # ---- vòng đời: poll lịch + nhắc họp ----
    def start(self) -> None:
        settings = self.manifest.settings
        poll_ms = max(1, int(settings.get("calendar_poll_mins", 30))) * 60_000
        self._first_poll = QTimer()
        self._first_poll.setSingleShot(True)
        self._first_poll.timeout.connect(self.request_calendar_sync)
        self._first_poll.start(FIRST_POLL_DELAY_MS)
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self.request_calendar_sync)
        self._poll_timer.start(poll_ms)
        if self.ctx.kv is not None:
            offsets = list(settings.get("remind_before_mins", [15, 5]))
            self._reminders = MeetingReminderService(self.ctx, self.calendar_repo, offsets)
            self._reminders.start()
            self._scheduled_briefing.start()
        self._focus_wiring.connect()

    def stop(self) -> None:
        for timer in (self._first_poll, self._poll_timer):
            if timer is not None:
                timer.stop()
        self._scheduled_briefing.stop()
        self._focus_wiring.disconnect()
        if self._reminders is not None:
            self._reminders.stop()

    def handle_action(self, action_id: str) -> None:
        handler = self._actions.get(action_id)
        if handler is None:
            logger.warning("Work engine không có action '%s'", action_id)
            return
        handler()

    # ---- briefing ----
    def on_pet_click(self) -> bool:
        """Click đầu tiên trong ngày (ngày local) → briefing; các click sau trả False để pet động viên."""
        today = self._clock().date().isoformat()
        if self.ctx.kv.get(LAST_BRIEFING_KEY) == today:
            return False
        self.show_briefing()
        return True

    def _last_briefing_dates(self) -> tuple[Optional[str], Optional[str]]:
        return self.ctx.kv.get(LAST_BRIEFING_KEY), self.ctx.kv.get(LAST_MIDDAY_BRIEFING_KEY)

    def show_briefing(self, slot: Optional[str] = None) -> None:
        """slot None (menu/click) → theo giờ hiện tại; timer truyền slot đến hạn. Đánh dấu KV trước khi chạy nên không bao giờ bắn đôi."""
        now = self._clock()
        slot = slot or slot_for_time(now, self.manifest.settings)
        date_keys = (LAST_BRIEFING_KEY, LAST_MIDDAY_BRIEFING_KEY) if slot == MIDDAY else (LAST_BRIEFING_KEY,)
        previous_at = mark_briefing_fired(self.ctx.kv, now, date_keys)  # chặn briefing dồn dập
        self._briefing.start(slot, previous_at=previous_at, now=now)

    # ---- tasks / ask / rocks / calendar ----
    def _open_tasks_list(self) -> None:
        if self.ctx.dashboard is not None:
            self.ctx.dashboard.open_tasks_list()

    def _open_ask(self) -> None:
        self.ctx.quick_chat.open_for(self.manifest.id)

    def _open_rocks_tab(self) -> None:
        dashboard = self.ctx.dashboard
        if dashboard is None:
            return
        if self._tab is not None and isValid(self._tab):
            self._tab.refresh()
            dashboard.tabs.setCurrentWidget(self._tab)
        dashboard.show()
        dashboard.raise_()
        dashboard.activateWindow()

    def today_events(self) -> list[tuple[datetime, str]]:
        return sorted(today_calendar_events(self.db_engine), key=lambda e: e[0].astimezone())

    def today_rows(self):
        """Mọi sự kiện cache của hôm nay (kể cả cả ngày) cho tab."""
        return self.calendar_repo.today()

    def _show_calendar(self) -> None:
        timed = [e for e in self.calendar_repo.today() if not e.all_day]
        now = datetime.now(timezone.utc)
        remaining = [e for e in timed if event_end(e) >= now]
        if remaining:
            lines = [f"{e.start_at.astimezone():%H:%M} {sanitize_untrusted_text(e.title)}" for e in remaining]
            text = "Lịch còn lại hôm nay: " + ", ".join(lines)
        elif timed:
            text = "Hôm nay hết lịch họp rồi, anh!"
        else:
            text = "Hôm nay chưa có lịch họp nào."
        if self.ctx.bubble is not None:
            self.ctx.bubble.show_message(text, mood="CHEER", timeout_ms=10_000)

    def calendar_status_text(self) -> str:
        """Dòng trạng thái cho tab: cảnh báo nếu lần sync gần nhất lỗi (cache cũ vẫn hiển thị)."""
        fetched = self.calendar_sync.fetched_at()
        stamp = f"{fetched.astimezone():%H:%M %d/%m}" if fetched else None
        if self.calendar_sync.last_ok is False:
            return f"⚠️ Lịch cập nhật lúc {stamp}" if stamp else "⚠️ Chưa đồng bộ được lịch"
        return f"Lịch cập nhật lúc {stamp}" if stamp else "Chưa đồng bộ lịch"

    def request_calendar_sync(self) -> None:
        """Poll nền (timer / nút 🔄); không có event loop thì bỏ qua."""
        coro = self._sync_and_refresh()
        try:
            spawn_background_task(coro, "work-calendar-sync")
        except RuntimeError:
            coro.close()

    async def _sync_and_refresh(self) -> None:
        await self.calendar_sync.sync()
        if self._tab is not None and isValid(self._tab):  # tab có thể đã bị deleteLater khi modules_changed
            self._tab.refresh()

    def build_dashboard_tab(self):
        from src.ui.module_tabs.work_rocks_and_calendar_tab_widget import WorkRocksAndCalendarTab

        self._tab = WorkRocksAndCalendarTab(self)  # widget mới mỗi lần: tab cũ bị deleteLater khi modules_changed
        return self._tab

    # ---- Rock CRUD (tab gọi vào đây) ----
    def add_rock(self, title: str, detail: str = "") -> Rock:
        rock = self.rocks.add(title, detail)
        self._sync_rock("thêm", rock)
        return rock

    def resolve_rock(self, rock_id: str, note: str = "") -> Optional[Rock]:
        rock = self.rocks.set_status(rock_id, "resolved", note)
        if rock:
            self._sync_rock("đã giải quyết", rock)
        return rock

    def drop_rock(self, rock_id: str) -> Optional[Rock]:
        rock = self.rocks.set_status(rock_id, "dropped")
        if rock:
            self._sync_rock("bỏ", rock)
        return rock

    def move_task_to_rock(self, task_id: str) -> Optional[Rock]:
        from src.core.models import DatabaseManager
        db_mgr = DatabaseManager.for_engine(self.db_engine)
        rock = db_mgr.move_task_to_rock(task_id)
        if rock:
            self._sync_rock("thêm", rock)
            if self._tab is not None and isValid(self._tab):
                self._tab.refresh()
        return rock

    def move_rock_to_task(self, rock_id: str):
        from src.core.models import DatabaseManager
        rock = self.rocks.get(rock_id)
        if not rock:
            return None
        db_mgr = DatabaseManager.for_engine(self.db_engine)
        task = db_mgr.move_rock_to_task(rock_id)
        if task:
            self._sync_rock("chuyển sang Todo", rock)
            if self._tab is not None and isValid(self._tab):
                self._tab.refresh()
        return task

    def _sync_rock(self, action: str, rock: Rock) -> None:
        """Best-effort: gửi [ROCK_UPDATE] tới profile work ở nền; không có loop/kết nối thì bỏ qua."""
        client = self.ctx.client_pool.for_module(self.manifest.id) if self.ctx.client_pool else None
        if client is None:
            return
        coro = send_rock_update(client, format_rock_update(action, rock.title, rock_age_days(rock)))
        try:
            spawn_background_task(coro, "work-rock-sync")
        except RuntimeError:
            coro.close()
