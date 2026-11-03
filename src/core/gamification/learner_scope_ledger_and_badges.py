"""Phạm vi dữ liệu của MỘT learner (các module coach của 1 kết nối Hermes) cho báo cáo `learning`.

Con cái dùng profile Hermes riêng thì không được thấy dữ liệu của nhau:
- `ScopedXpLedger`: chỉ cộng XP event có source_module thuộc learner (không gồm work/core).
- Huy hiệu học tập: đánh giá lại trên dữ liệu RIÊNG của learner; chỉ giữ huy hiệu (đã mở toàn cục) mà learner tự đạt.
- Phiên Họp/Học nhóm không gắn với module nên không quy được cho ai: chỉ đưa vào khi chỉ có 1 learner (`include_meetings`).
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, FrozenSet, List, Set, Tuple

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from src.core.gamification.badge_catalog_loader import CatalogError, load_badge_catalog
from src.core.gamification.badge_unlock_evaluator import evaluate
from src.core.gamification.gamification_table_models import XpEvent
from src.core.gamification.level_progression_engine import week_start_of
from src.core.gamification.lifetime_totals_builder import build_lifetime_totals
from src.core.gamification.week_context_builder import build_week_context, to_window_data_by_kind
from src.core.gamification.xp_ledger_repository import XpLedgerRepository, local_date_of


@dataclass(frozen=True)
class LearnerScope:
    modules: FrozenSet[str]
    include_meetings: bool = False


class ScopedXpLedger(XpLedgerRepository):
    """Sổ cái chỉ nhìn thấy event của module thuộc `scope` (ghi vẫn dùng add() gốc, nhưng báo cáo chỉ đọc)."""

    def __init__(self, engine: Engine, scope: LearnerScope):
        super().__init__(engine)
        self.scope = scope

    def _where(self):
        return XpEvent.source_module.in_(sorted(self.scope.modules))

    def daily_totals(self, start: date, end: date) -> Dict[date, int]:
        totals: Dict[date, int] = {}
        with Session(self._engine) as s:
            rows = s.exec(select(XpEvent.local_date, XpEvent.xp).where(
                XpEvent.local_date >= start.isoformat(), XpEvent.local_date <= end.isoformat(), self._where())).all()
        for day, xp in rows:
            d = date.fromisoformat(day)
            totals[d] = totals.get(d, 0) + xp
        return totals

    def kind_counts_by_day(self, start: date, end: date) -> Dict[date, Counter]:
        out: Dict[date, Counter] = {}
        with Session(self._engine) as s:
            rows = s.exec(select(XpEvent.local_date, XpEvent.kind).where(
                XpEvent.local_date >= start.isoformat(), XpEvent.local_date <= end.isoformat(), self._where())).all()
        for day, kind in rows:
            out.setdefault(date.fromisoformat(day), Counter())[kind] += 1
        return out

    def lifetime_counts(self) -> Counter:
        with Session(self._engine) as s:
            return Counter(s.exec(select(XpEvent.kind).where(self._where())).all())

    def first_event_date(self):
        with Session(self._engine) as s:
            first = s.exec(select(XpEvent.local_date).where(self._where()).order_by(XpEvent.local_date).limit(1)).first()
        return date.fromisoformat(first) if first else None


def scoped_learning_unlocks(engine: Engine, ledger: ScopedXpLedger, wellbeing, unlocks, learn: Set[str],
                            until: date) -> List[Tuple[str, str, date]]:
    """[(badge_id, week_start, ngày mở)] huy hiệu học tập mở ≤ `until` mà learner tự đạt trên dữ liệu riêng."""
    rows = [(r.badge_id, r.week_start, local_date_of(r.unlocked_at)) for r in unlocks.list_all()
            if r.badge_id in learn and local_date_of(r.unlocked_at) <= until]
    if not rows:
        return []
    try:
        catalog = load_badge_catalog()
    except CatalogError:
        return []
    satisfied: Dict[str, Set[str]] = {}
    for week in {w for _, w, _ in rows}:
        start = date.fromisoformat(week)
        today = min(until, start + timedelta(days=6)) if week_start_of(until) == start else start + timedelta(days=7)
        ctx = build_week_context(engine, ledger, wellbeing, start, today)
        windows = to_window_data_by_kind(ctx, build_lifetime_totals(engine, ledger, today))
        satisfied[week] = set(evaluate(catalog, windows, set(), set()))
    return [r for r in rows if r[0] in satisfied[r[1]]]
