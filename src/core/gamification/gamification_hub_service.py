"""Facade Qt duy nhất của gamification: nối tín hiệu app -> reconciler/heartbeat -> HubSnapshot + bubble.

UI (phase 06/07/08) chỉ cần: `snapshot_changed`, `level_changed`, `badges_unlocked`, `current_snapshot`, `refresh()`,
và các repo công khai (`ledger`, `wellbeing`, `unlocks`, `snapshots`, `heartbeat`). Mọi lỗi DB đều bị bắt + log.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any, Callable, List, Optional

from PySide6.QtCore import QObject, QTimer, Signal
from sqlalchemy.engine import Engine

from src.core.app_state_key_value_store import KeyValueStore
from src.core.gamification.app_heartbeat_and_away_tracker import AppHeartbeatTracker
from src.core.gamification.badge_catalog_loader import BadgeDef
from src.core.gamification.badge_unlock_repository import BadgeUnlockRepository
from src.core.gamification.badge_unlock_service import BadgeUnlockService
from src.core.gamification.gamification_hub_bubble_messages import PendingBubble, compose_unlock_message
from src.core.gamification.gamification_columns_migration import ensure_gamification_columns
from src.core.gamification.hub_snapshot_builder import build_hub_snapshot
from src.core.gamification.hub_snapshot_model import HubSnapshot
from src.core.gamification.level_progression_engine import week_start_of
from src.core.gamification.skin_unlock_service import SkinUnlockService
from src.core.gamification.weekly_snapshot_service import WeeklySnapshotService
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.xp_ledger_repository import XpLedgerRepository
from src.core.gamification.xp_source_reconciler import XpSourceReconciler
from src.core.i18n import tr

logger = logging.getLogger("ted")

KV_LAST_LEVEL = "gamify.last_level"       # "<thứ Hai ISO>:<level>"
DEBOUNCE_MS = 1500
INITIAL_REFRESH_MS = 3000
TICK_MS = 60_000
REFRESH_EVERY_TICKS = 5
BREAK_STATE = "BREAK_RUNNING"


class GamificationHubService(QObject):
    snapshot_changed = Signal(object)    # HubSnapshot
    level_changed = Signal(int, int)     # (level cũ, level mới) - chỉ trong cùng tuần
    badges_unlocked = Signal(list)       # list[BadgeDef] mới mở
    skins_unlocked = Signal(list)        # list[UnlockableSkin] nhân vật mới mở

    def __init__(self, ctx: Any, engine: Engine, parent: Optional[QObject] = None, skins: Optional[list] = None):
        super().__init__(parent)
        self._ctx, self._engine = ctx, engine
        self.kv = getattr(ctx, "kv", None) or KeyValueStore(engine)
        ensure_gamification_columns(engine)  # DB dev cũ thiếu cột thêm sau phase 01
        self.ledger = XpLedgerRepository(engine)
        self.wellbeing = WellbeingDailyRepository(engine)
        self.unlocks = BadgeUnlockRepository(engine)
        self.heartbeat = AppHeartbeatTracker(self.kv, self.wellbeing, self.ledger)
        self.snapshots = WeeklySnapshotService(engine, self.ledger, self.wellbeing, self.unlocks, self.kv)
        self._badges: Optional[BadgeUnlockService] = None
        try:
            self._badges = BadgeUnlockService(engine, self.ledger, self.wellbeing, self.unlocks)
        except Exception:  # noqa: BLE001 - catalog hỏng: vẫn chạy XP/level, không có badge
            logger.exception("Không khởi tạo được BadgeUnlockService")
        self.reconciler = XpSourceReconciler(engine, self.ledger, self.kv, self._module_engine_of)
        self.current_snapshot: Optional[HubSnapshot] = None
        self.skin_unlocks: Optional[SkinUnlockService] = self._build_skin_unlocks(skins)
        self._bubble = PendingBubble(ctx)
        self._ticks = 0
        self._debounce = self._timer(DEBOUNCE_MS, True, self.refresh)
        self._tick_timer = self._timer(TICK_MS, False, self._on_tick)
        self._started = False

    def _build_skin_unlocks(self, skins: Optional[list]) -> Optional[SkinUnlockService]:
        """Mở khoá nhân vật bundle; lỗi → None (cổng tắt = dùng được hết). Skin đã lưu mà đang khoá → về mặc định."""
        try:
            from src.config import DEFAULT_CHARACTER_SKIN, UNLOCKABLE_SKINS, settings
            from src.core.skin_unlock_gate import is_skin_unlocked
            service = SkinUnlockService(self._engine, self.ledger, UNLOCKABLE_SKINS if skins is None else skins)
            if not is_skin_unlocked(settings.character_skin):
                settings.character_skin = DEFAULT_CHARACTER_SKIN
                settings.save()
            return service
        except Exception:  # noqa: BLE001 - gamification không được làm hỏng app
            logger.exception("Không khởi tạo được SkinUnlockService")
            return None

    def _timer(self, ms: int, single: bool, slot: Callable[[], None]) -> QTimer:
        t = QTimer(self)
        t.setSingleShot(single)
        t.setInterval(ms)
        t.timeout.connect(slot)
        return t

    def _module_engine_of(self, module_id: str) -> str:
        """Engine của module theo registry; module lạ -> coach (chỉ dữ liệu coach cần map)."""
        try:
            manifest = self._ctx.registry.get(module_id) if self._ctx.registry else None
        except Exception:  # noqa: BLE001
            manifest = None
        return getattr(manifest, "engine", None) or "coach"

    # ---- vòng đời ----
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._safe("on_app_start", lambda: self.heartbeat.on_app_start(datetime.now(timezone.utc)))
        focus = getattr(self._ctx, "focus_engine", None)
        if focus is not None:
            focus.session_completed.connect(lambda *_: self.request_refresh())
            focus.tasks_updated.connect(self.request_refresh)
            focus.state_changed.connect(self._on_focus_state)
            meeting_done = getattr(focus, "meeting_completed", None)   # họp xong → XP họp + Gắn kết hiện ngay
            if meeting_done is not None:
                meeting_done.connect(lambda *_: self.request_refresh())
        self._connect_untangle()
        self._tick_timer.start()
        QTimer.singleShot(INITIAL_REFRESH_MS, lambda: self._started and self.refresh())

    def _connect_untangle(self) -> None:
        try:
            from src.core.idea_untangle.idea_untangle_service_and_completion_signal import idea_untangle_service
            idea_untangle_service.session_completed.connect(lambda *_: self.request_refresh())
        except Exception:  # noqa: BLE001 - module Gỡ Rối chưa có/lỗi: bỏ qua
            logger.info("Bỏ qua nối tín hiệu Gỡ Rối cho Hub", exc_info=True)

    def stop(self) -> None:
        self._started = False
        self._tick_timer.stop()
        self._debounce.stop()
        self._safe("final_tick", lambda: self.heartbeat.tick(datetime.now(timezone.utc)))

    # ---- sự kiện ----
    def _on_focus_state(self, state: Any, _mood: str = "") -> None:
        if self._started and str(getattr(state, "value", state)) == BREAK_STATE:
            self._safe("record_break", lambda: self.heartbeat.record_break(datetime.now(timezone.utc)))

    def _on_tick(self) -> None:
        self._safe("tick", lambda: self.heartbeat.tick(datetime.now(timezone.utc)))
        self._ticks += 1
        if self._ticks % REFRESH_EVERY_TICKS == 0:
            self.refresh()
        else:
            self._bubble.flush()

    def request_refresh(self) -> None:
        """Debounce 1.5s: nhiều tín hiệu liên tiếp (stop_session phát 2) -> 1 lần refresh."""
        if self._started and not self._debounce.isActive():   # đã stop() (vd khởi động Hub hỏng giữa chừng) → bỏ qua
            self._debounce.start()

    def _safe(self, name: str, fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except Exception:  # noqa: BLE001 - gamification không được làm hỏng luồng chính
            logger.exception("Gamification %s thất bại", name)
            return None

    # ---- refresh ----
    def refresh(self) -> Optional[HubSnapshot]:
        try:
            today, now = date.today(), datetime.now(timezone.utc)
            self.reconciler.run(now)
            self.snapshots.refresh_if_week_changed(today)
            new_badges: List[BadgeDef] = self._badges.refresh(today) if self._badges else []
            snap = build_hub_snapshot(self._engine, self.ledger, self.wellbeing, self.unlocks, self.snapshots, today)
        except Exception:  # noqa: BLE001
            logger.exception("Gamification refresh thất bại")
            return None
        self.current_snapshot = snap
        self._announce_level(snap)
        new_skins = (self._safe("skin_unlocks", lambda: self.skin_unlocks.refresh(snap)) or []) if self.skin_unlocks else []
        message = compose_unlock_message(new_badges, new_skins)
        if message:
            self._bubble.say(message)
        if new_badges:
            self.badges_unlocked.emit(new_badges)
        if new_skins:
            self.skins_unlocked.emit(new_skins)
        self.snapshot_changed.emit(snap)
        self._bubble.flush()
        return snap

    def _announce_level(self, snap: HubSnapshot) -> None:
        """So level với KV (kèm tuần): chỉ báo khi đổi level trong cùng tuần; sang tuần mới chỉ cập nhật mốc."""
        week = week_start_of(snap.today).isoformat()
        raw = self.kv.get(KV_LAST_LEVEL) or ""
        old_week, _, old_level = raw.partition(":")
        self.kv.set(KV_LAST_LEVEL, f"{week}:{snap.level}")
        if old_week != week or not old_level.isdigit() or int(old_level) == snap.level:
            return
        old = int(old_level)
        self._bubble.say(tr("hub_level_up_bubble" if snap.level > old else "hub_level_down_bubble", level=snap.level))
        self.level_changed.emit(old, snap.level)
