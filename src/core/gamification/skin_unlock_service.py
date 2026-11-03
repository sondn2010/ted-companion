"""Mở khoá nhân vật bundle: đánh giá điều kiện từng nhân vật khi Hub refresh, lưu vĩnh viễn vào bảng SkinUnlock.

Không Qt. Hub service gọi `refresh(snapshot)` → danh sách nhân vật MỚI mở (để hiện bubble) và cập nhật cổng
`skin_unlock_gate`. Mở khoá chỉ thêm, không bao giờ thu hồi (kể cả khi level tuần reset).
"""

import logging
from datetime import date
from typing import Dict, List, Set, Tuple

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from src.core.gamification.gamification_table_models import SkinUnlock, WeeklySnapshot
from src.core.gamification.hub_snapshot_model import HubSnapshot
from src.core.gamification.lifetime_totals_builder import build_lifetime_totals
from src.core.gamification.xp_ledger_repository import XpLedgerRepository
from src.core.skin_unlock_gate import set_unlocked_skin_keys
from src.core.unlockable_skin_condition_evaluator import SkinProgressInputs, condition_progress, is_condition_met
from src.core.unlockable_skin_registry_model import UnlockableSkin

logger = logging.getLogger("ted")


class SkinUnlockRepository:
    def __init__(self, engine: Engine):
        self._engine = engine
        SkinUnlock.__table__.create(engine, checkfirst=True)

    def keys(self) -> Set[str]:
        with Session(self._engine) as s:
            return set(s.exec(select(SkinUnlock.character_key)).all())

    def add(self, key: str) -> bool:
        """Idempotent: False nếu đã có."""
        with Session(self._engine) as s:
            if s.get(SkinUnlock, key) is not None:
                return False
            s.add(SkinUnlock(character_key=key))
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                return False
            return True


class SkinUnlockService:
    def __init__(self, engine: Engine, ledger: XpLedgerRepository, skins: List[UnlockableSkin]):
        self._engine, self._ledger = engine, ledger
        self.skins = list(skins)
        self.repo = SkinUnlockRepository(engine)
        self.inputs = SkinProgressInputs()
        self._unlocked: Set[str] = set()
        # 'free' mở ngay từ đầu (trước refresh đầu tiên) → skin free đã lưu không bị đưa về mặc định lúc khởi động
        free = {s.key for s in self.skins if s.condition.type == "free"}
        self._publish((self.repo.keys() & {s.key for s in self.skins}) | free)

    @property
    def unlocked_keys(self) -> Set[str]:
        return set(self._unlocked)

    def _publish(self, keys: Set[str]) -> None:
        self._unlocked = set(keys)
        set_unlocked_skin_keys(self._unlocked)

    def _build_inputs(self, snap: HubSnapshot) -> SkinProgressInputs:
        totals = build_lifetime_totals(self._engine, self._ledger, snap.today)
        with Session(self._engine) as s:
            past_peak = s.exec(select(func.max(WeeklySnapshot.peak_level))).one() or 1
        totals["untangle_sessions"] = float(self._ledger.lifetime_counts()["idea_untangled"])
        totals["peak_level"] = float(max(past_peak, snap.peak_level))
        return SkinProgressInputs(frozenset(snap.badges_unlocked), totals)

    def refresh(self, snap: HubSnapshot) -> List[UnlockableSkin]:
        """Lưu nhân vật mới đạt điều kiện; trả danh sách nhân vật mới mở (trừ loại 'free' — không cần ăn mừng)."""
        self.inputs = self._build_inputs(snap)
        unlocked = self.repo.keys()
        newly: List[UnlockableSkin] = []
        for skin in self.skins:
            if skin.key not in unlocked and is_condition_met(skin.condition, self.inputs) and self.repo.add(skin.key):
                unlocked.add(skin.key)
                if skin.condition.type != "free":
                    newly.append(skin)
        self._publish(unlocked & {s.key for s in self.skins})
        return newly

    def progress_of(self, skin: UnlockableSkin) -> Tuple[float, float]:
        """(hiện tại, mục tiêu) đã kẹp theo mục tiêu; đã mở khoá → đầy."""
        current, target = condition_progress(skin.condition, self.inputs)
        return (target, target) if skin.key in self._unlocked else (min(current, target), target)

    def progress_map(self) -> Dict[str, Tuple[float, float]]:
        return {s.key: self.progress_of(s) for s in self.skins}
