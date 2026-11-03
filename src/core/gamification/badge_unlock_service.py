"""Đánh giá huy hiệu cho tuần hiện tại (live) + lưu BadgeUnlock. Hub service gọi refresh() định kỳ và phát bubble."""

from datetime import date
from typing import List, Optional

from sqlalchemy.engine import Engine

from src.core.gamification.badge_catalog_loader import BadgeCatalog, BadgeDef, load_badge_catalog
from src.core.gamification.badge_unlock_evaluator import evaluate
from src.core.gamification.badge_unlock_repository import BadgeUnlockRepository
from src.core.gamification.level_progression_engine import week_start_of
from src.core.gamification.lifetime_totals_builder import build_lifetime_totals
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.week_context_builder import build_week_context, prev_week_info, to_window_data_by_kind
from src.core.gamification.xp_ledger_repository import XpLedgerRepository


class BadgeUnlockService:
    def __init__(self, engine: Engine, ledger: XpLedgerRepository, wellbeing: WellbeingDailyRepository,
                 unlocks: BadgeUnlockRepository, catalog: Optional[BadgeCatalog] = None):
        self._engine, self._ledger, self._wellbeing, self._unlocks = engine, ledger, wellbeing, unlocks
        self._catalog = catalog or load_badge_catalog()

    def refresh(self, today: date) -> List[BadgeDef]:
        """Tính tuần hiện tại, lưu huy hiệu mới đạt, trả danh sách BadgeDef mới (để hiện bubble)."""
        week = week_start_of(today)
        prev_xp, prev_level = prev_week_info(self._engine, week)
        ctx = build_week_context(self._engine, self._ledger, self._wellbeing, week, today, prev_xp, prev_level)
        windows = to_window_data_by_kind(ctx, build_lifetime_totals(self._engine, self._ledger, today))
        key = week.isoformat()
        ids = evaluate(self._catalog, windows, self._unlocks.ids_for_week(key), self._unlocks.ever_unlocked_ids())
        by_id = {b.id: b for b in self._catalog.badges}
        return [by_id[i] for i in ids if self._unlocks.add(i, key)]
