"""Nhật ký tuần: đóng băng mỗi tuần đã kết thúc vào WeeklySnapshot (+ mở huy hiệu day/week lịch sử), idempotent."""

import json
import logging
from datetime import date, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from src.core.app_state_key_value_store import KeyValueStore
from src.core.gamification.badge_catalog_loader import BadgeCatalog, CatalogError, load_badge_catalog
from src.core.gamification.badge_unlock_evaluator import evaluate
from src.core.gamification.badge_unlock_repository import BadgeUnlockRepository
from src.core.gamification.gamification_table_models import WeeklySnapshot
from src.core.gamification.level_progression_engine import week_start_of
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.week_context_builder import (
    build_week_context, stats_json, to_window_data_by_kind)
from src.core.gamification.xp_ledger_repository import XpLedgerRepository

logger = logging.getLogger("ted")

KV_LAST_WEEK = "gamify.last_week"
BACKFILL_MAX_WEEKS = 52


class WeeklySnapshotService:
    def __init__(self, engine: Engine, ledger: XpLedgerRepository, wellbeing: WellbeingDailyRepository,
                 unlocks: BadgeUnlockRepository, kv: Optional[KeyValueStore] = None,
                 catalog: Optional[BadgeCatalog] = None):
        self._engine, self._ledger, self._wellbeing, self._unlocks = engine, ledger, wellbeing, unlocks
        self._kv = kv
        self._catalog = catalog
        WeeklySnapshot.__table__.create(engine, checkfirst=True)

    def _catalog_or_none(self) -> Optional[BadgeCatalog]:
        if self._catalog is None:
            try:
                self._catalog = load_badge_catalog()
            except CatalogError:
                logger.warning("Không đọc được badge catalog, snapshot bỏ qua huy hiệu", exc_info=True)
        return self._catalog

    def backfill(self, today: date) -> int:
        """Thêm snapshot cho mọi tuần đã kết thúc còn thiếu (tối đa 52 tuần, từ tuần có event đầu tiên).
        Tuần hoàn toàn trống không có hàng (khoảng trống hiện rõ trong nhật ký). Trả số hàng mới."""
        first = self._ledger.first_event_date()
        if first is None:
            return 0
        this_week = week_start_of(today)
        start = max(week_start_of(first), this_week - timedelta(weeks=BACKFILL_MAX_WEEKS))
        with Session(self._engine) as s:
            rows = {r.week_start: (r.xp_earned, r.final_level) for r in s.exec(select(WeeklySnapshot)).all()}
        catalog, inserted, week = self._catalog_or_none(), 0, start
        while week < this_week:
            key = week.isoformat()
            if key not in rows:
                row = self._build_snapshot(week, rows.get((week - timedelta(days=7)).isoformat()), catalog)
                if row is not None:
                    rows[key] = (row.xp_earned, row.final_level)  # đọc trước khi commit làm hết hạn thuộc tính
                    with Session(self._engine, expire_on_commit=False) as s:  # không hết hạn → không DetachedInstanceError
                        s.add(row)
                        s.commit()
                    inserted += 1
            week += timedelta(days=7)
        return inserted

    def _build_snapshot(self, week: date, prev: Optional[Tuple[int, int]],
                        catalog: Optional[BadgeCatalog]) -> Optional[WeeklySnapshot]:
        ctx = build_week_context(self._engine, self._ledger, self._wellbeing, week, week + timedelta(days=7),
                                 prev[0] if prev else 0, prev[1] if prev else None)
        if not ctx.has_any_activity():
            return None
        key = week.isoformat()
        if catalog is not None:  # lifetime không xét ở backfill (không biết "tại thời điểm đó")
            for badge_id in evaluate(catalog, to_window_data_by_kind(ctx), self._unlocks.ids_for_week(key)):
                self._unlocks.add(badge_id, key)
        # mọi huy hiệu mở trong tuần (cả bản mở live lúc tuần đang chạy), không chỉ phần backfill vừa tìm thêm
        badges: List[str] = sorted(self._unlocks.ids_for_week(key))
        totals = self._ledger.daily_totals(week, week + timedelta(days=6))
        return WeeklySnapshot(
            week_start=key, final_level=ctx.progress.level, peak_level=ctx.progress.peak_level,
            xp_earned=sum(v for v in totals.values() if v > 0), final_pct=ctx.progress.pct,
            active_days=ctx.progress.active_days, decay_days=ctx.progress.decay_days,
            stats_json=stats_json(ctx), badges_json=json.dumps(badges))

    def refresh_if_week_changed(self, today: date) -> int:
        """Gọi mỗi lần refresh: chỉ backfill khi tuần đổi so với KV gamify.last_week (không KV → luôn backfill)."""
        current = week_start_of(today).isoformat()
        if self._kv is not None and self._kv.get(KV_LAST_WEEK) == current:
            return 0
        inserted = self.backfill(today)
        if self._kv is not None:
            self._kv.set(KV_LAST_WEEK, current)
        return inserted

    def list_recent(self, n: int = 12) -> List[WeeklySnapshot]:
        """n tuần gần nhất đã lưu, mới nhất trước (tuần hiện tại tính live ở Hub, không lưu)."""
        with Session(self._engine) as s:
            return list(s.exec(select(WeeklySnapshot).order_by(WeeklySnapshot.week_start.desc()).limit(n)).all())

    @staticmethod
    def badges_of(row: WeeklySnapshot) -> List[str]:
        try:
            return list(json.loads(row.badges_json))
        except ValueError:
            return []
