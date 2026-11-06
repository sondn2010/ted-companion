"""Regression tests từ code review gamification core (2026-10-22)."""

import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from sqlmodel import Session

from src.core.app_state_key_value_store import KeyValueStore
from src.core.gamification.badge_catalog_loader import load_badge_catalog
from src.core.gamification.badge_unlock_repository import BadgeUnlockRepository
from src.core.gamification.weekly_snapshot_service import WeeklySnapshotService
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.xp_ledger_repository import XpLedgerRepository
from src.core.gamification.xp_source_reconciler import KV_CURSOR, XpSourceReconciler
from src.core.models import FocusSession


def _local_noon(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, 0).astimezone().astimezone(timezone.utc)


def test_snapshot_badges_json_keeps_badges_unlocked_live_during_the_week(memory_engine):
    ledger, unlocks = XpLedgerRepository(memory_engine), BadgeUnlockRepository(memory_engine)
    svc = WeeklySnapshotService(memory_engine, ledger, WellbeingDailyRepository(memory_engine), unlocks,
                                catalog=load_badge_catalog(strict=True))
    for i in range(5):   # tuần 2026-10-12: 5 task → tasks_week_bronze
        ledger.add(f"task_done:t{i}:1", _local_noon(date(2026, 10, 13)), "work", "work", "task_done")
    unlocks.add("focus_day_bronze", "2026-10-12")          # đã mở live khi tuần còn chạy
    assert svc.backfill(date(2026, 10, 22)) == 1
    badges = svc.badges_of(svc.list_recent()[0])
    assert {"focus_day_bronze", "tasks_week_bronze"} <= set(badges)


def test_reconciler_cursor_in_future_after_clock_change_still_scans(memory_engine):
    ledger, kv = XpLedgerRepository(memory_engine), KeyValueStore(memory_engine)
    rec = XpSourceReconciler(memory_engine, ledger, kv, lambda mid: "coach")
    now = datetime.now(timezone.utc)
    kv.set(KV_CURSOR, (now + timedelta(hours=3)).isoformat())   # đồng hồ từng chạy nhanh rồi bị chỉnh lùi
    with Session(memory_engine) as s:
        s.add(FocusSession(actual_minutes=25, distraction_count=1, focus_rating=5, ended_at=now - timedelta(minutes=30)))
        s.commit()
    assert rec.run(now) == 1


def test_hub_service_refreshes_after_meeting_completed(memory_engine):
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])  # noqa: F841
    from src.core.gamification.gamification_hub_service import GamificationHubService

    class _Focus(QObject):
        session_completed = Signal(str, int, int)
        tasks_updated = Signal()
        state_changed = Signal(str, str)
        meeting_completed = Signal(str, int)

    focus = _Focus()
    ctx = SimpleNamespace(kv=KeyValueStore(memory_engine), focus_engine=focus, registry=None,
                          bubble=SimpleNamespace(is_busy=lambda: False, show_message=lambda *a, **k: None))
    hub = GamificationHubService(ctx, memory_engine, skins=[])
    hub.start()
    try:
        assert not hub._debounce.isActive()
        focus.meeting_completed.emit("team_meeting", 45)
        assert hub._debounce.isActive()
    finally:
        hub.stop()
