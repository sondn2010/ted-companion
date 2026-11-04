"""Dữ liệu giả thực tế cho test/ảnh chụp trang Hub: snapshot đầy đủ + service giả (QObject có đủ tín hiệu)."""

from datetime import date
from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal

from src.core.gamification.badge_catalog_loader import load_badge_catalog
from src.core.gamification.hub_snapshot_model import HubSnapshot, WeeklyLogRow

TODAY = date(2026, 10, 22)
WEEK = date(2026, 10, 19)


def make_snapshot(level=6, xp_today=12, badges=None) -> HubSnapshot:
    ids = [b.id for b in load_badge_catalog().badges]
    owned = frozenset(ids[:17] if badges is None else badges)
    log = [WeeklyLogRow(f"2026-{m:02d}-{d:02d}", lv, pk, lv * 10 - 3.0, xp, act, dec, {}, ids[:n])
           for (m, d, lv, pk, xp, act, dec, n) in [
               (10, 12, 5, 6, 720, 6, 1, 3), (10, 5, 4, 4, 510, 5, 2, 1), (9, 28, 4, 5, 560, 6, 1, 2),
               (9, 21, 3, 3, 300, 4, 3, 0), (9, 14, 3, 3, 330, 4, 2, 1)]]
    return HubSnapshot(
        today=TODAY, week_start=WEEK, level=level, peak_level=level, pct=level * 10 - 3.0,
        pct_today_delta=4.0, xp_today=xp_today, week_xp=310, active_days=3, decay_days=0,
        stats={"energy": 68, "data": 74, "learning": 55, "screen_load": 82, "engagement": 40, "health": 61},
        stats_delta_today={"energy": 3, "data": 6, "learning": 0, "screen_load": 5, "engagement": -2, "health": 1},
        badges_unlocked=owned, badges_this_week=frozenset(list(owned)[:2]), distinct_badge_count=len(owned),
        weekly_log=log)


class FakeHubService(QObject):
    snapshot_changed = Signal(object)
    level_changed = Signal(int, int)

    def __init__(self, wellbeing, snapshot=None):
        super().__init__()
        self.wellbeing = wellbeing
        self.current_snapshot = snapshot
        self.skin_unlocks = None
        self.refresh_requests = 0

    def request_refresh(self):
        self.refresh_requests += 1


def fake_focus_engine():
    return SimpleNamespace(
        tasks_updated=SimpleNamespace(connect=lambda f: None),
        character_changed=SimpleNamespace(connect=lambda f: None),
        set_character=lambda k: None,
    )
