"""Kho câu hỏi: chèn chống trùng, chọn câu đến hạn/câu mới, đếm câu chưa hỏi, áp srs_overrides, gắn cờ."""

import logging
from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select

from src.engines.coach.coach_data_models import Attempt, QuizItem, ReviewState, content_hash, open_session
from src.engines.coach.coach_quiz_writing_report_schemas import GeneratedQuizItem
from src.engines.coach.coach_sync_plan_schemas import SrsOverride
from src.engines.coach.utc_aware_datetime_type import require_aware

logger = logging.getLogger("ted")


def _active(module_id: str):
    """Điều kiện chung: thuộc module, không bị gắn cờ, không bị retire."""
    return (QuizItem.module_id == module_id, col(QuizItem.flagged).is_(False), col(QuizItem.retired).is_(False))


def _unseen_where(module_id: str, topic: Optional[str], types: Optional[Sequence[str]]):
    conds = [*_active(module_id), col(QuizItem.id).not_in(select(ReviewState.item_id))]
    if topic:
        conds.append(QuizItem.topic == topic)
    if types:
        conds.append(col(QuizItem.type).in_(list(types)))
    return conds


class CoachItemRepository:
    def __init__(self, engine):
        self.engine = engine

    # ---- chèn câu hỏi ----
    def insert_items_dedup(self, module_id: str, items: Sequence[GeneratedQuizItem], now: datetime) -> int:
        """Chèn các câu chưa có (theo content_hash); trả về số câu thực sự chèn."""
        require_aware(now)
        rows: dict[str, QuizItem] = {}
        for item in items:
            digest = content_hash(item.topic, item.question)
            rows.setdefault(digest, QuizItem(
                module_id=module_id, topic=item.topic, type=item.type, question=item.question,
                choices_json=item.choices_json(), hints_json=item.hints_json(), answer=item.answer,
                explanation=item.explanation, difficulty=item.difficulty, content_hash=digest, created_at=now,
            ))
        if not rows:
            return 0
        with open_session(self.engine) as session:
            existing = set(session.exec(
                select(QuizItem.content_hash).where(QuizItem.module_id == module_id,
                                                    col(QuizItem.content_hash).in_(list(rows)))
            ).all())
            fresh = [row for digest, row in rows.items() if digest not in existing]
            payloads = [row.model_dump() for row in fresh]   # bản sao an toàn cho nhánh thử lại từng câu
            try:
                session.add_all(fresh)
                session.commit()
                return len(fresh)
            except IntegrityError:
                # Đua ghi giữa 2 tiến trình: thử từng câu, bỏ câu trùng
                session.rollback()
        inserted = 0
        for payload in payloads:
            with open_session(self.engine) as session:
                try:
                    session.add(QuizItem(**payload))
                    session.commit()
                    inserted += 1
                except IntegrityError:
                    session.rollback()
        return inserted

    def recent_questions(self, module_id: str, limit: int = 20) -> list[str]:
        with open_session(self.engine) as session:
            stmt = select(QuizItem.question).where(QuizItem.module_id == module_id) \
                .order_by(col(QuizItem.created_at).desc()).limit(limit)
            return list(session.exec(stmt).all())

    def get(self, item_id: str) -> Optional[QuizItem]:
        with open_session(self.engine) as session:
            return session.get(QuizItem, item_id)

    # ---- đếm / chọn ----
    def unseen_count(self, module_id: str, topic: Optional[str] = None, types: Optional[Sequence[str]] = None) -> int:
        with open_session(self.engine) as session:
            stmt = select(func.count()).select_from(QuizItem).where(*_unseen_where(module_id, topic, types))
            return session.exec(stmt).one()

    def _due_stmt(self, module_id: str, now: datetime, topic: Optional[str]):
        stmt = select(QuizItem).join(ReviewState, col(ReviewState.item_id) == col(QuizItem.id)) \
            .where(*_active(module_id), ReviewState.due_at <= now)
        return stmt.where(QuizItem.topic == topic) if topic else stmt

    def due_count(self, module_id: str, now: datetime, topic: Optional[str] = None) -> int:
        with open_session(self.engine) as session:
            sub = self._due_stmt(module_id, require_aware(now), topic).subquery()
            return session.exec(select(func.count()).select_from(sub)).one()

    def new_seen_count(self, module_id: str, since: datetime) -> int:
        """Số câu có lần trả lời ĐẦU TIÊN kể từ `since` (đầu ngày địa phương) → hạn mức new_per_day."""
        with open_session(self.engine) as session:
            sub = select(Attempt.item_id).where(Attempt.module_id == module_id) \
                .group_by(Attempt.item_id).having(func.min(Attempt.answered_at) >= require_aware(since, "since")).subquery()
            return session.exec(select(func.count()).select_from(sub)).one()

    def select_for_review(
        self, module_id: str, now: datetime, limit: int, new_per_day: int, day_start: datetime,
        topic: Optional[str] = None,
    ) -> list[QuizItem]:
        """Câu đến hạn (hộp thấp trước, due sớm trước), rồi câu mới tới hết hạn mức new_per_day trong ngày."""
        require_aware(now)
        with open_session(self.engine) as session:
            stmt = self._due_stmt(module_id, now, topic).order_by(ReviewState.box, ReviewState.due_at).limit(limit)
            picked = list(session.exec(stmt).all())
        new_room = min(limit - len(picked), max(0, new_per_day - self.new_seen_count(module_id, day_start)))
        if new_room > 0:
            with open_session(self.engine) as session:
                stmt = select(QuizItem).where(*_unseen_where(module_id, topic, None)) \
                    .order_by(col(QuizItem.created_at), col(QuizItem.id)).limit(new_room)
                picked.extend(session.exec(stmt).all())
        return picked

    def first_unseen(self, module_id: str, topic: Optional[str], types: Optional[Sequence[str]]) -> Optional[QuizItem]:
        """Câu chưa hỏi cũ nhất theo topic/types (dùng cho agenda `step`)."""
        with open_session(self.engine) as session:
            stmt = select(QuizItem).where(*_unseen_where(module_id, topic, types))                 .order_by(col(QuizItem.created_at), col(QuizItem.id)).limit(1)
            return session.exec(stmt).first()

    def flagged_items(self, module_id: str) -> list[QuizItem]:
        with open_session(self.engine) as session:
            stmt = select(QuizItem).where(QuizItem.module_id == module_id, col(QuizItem.flagged).is_(True))                 .order_by(col(QuizItem.created_at))
            return list(session.exec(stmt).all())

    def unflag_item(self, item_id: str) -> bool:
        with open_session(self.engine) as session:
            item = session.get(QuizItem, item_id)
            if item is None:
                return False
            item.flagged, item.flag_reason = False, ""
            session.add(item)
            session.commit()
            return True

    # ---- cờ / override ----
    def flag_item(self, item_id: str, reason: str) -> bool:
        with open_session(self.engine) as session:
            item = session.get(QuizItem, item_id)
            if item is None:
                return False
            item.flagged, item.flag_reason = True, reason
            session.add(item)
            session.commit()
            return True

    def apply_overrides(self, module_id: str, overrides: Sequence[SrsOverride], now: datetime) -> int:
        """retire → retired=True; reset → hộp 0, đến hạn ngay. id lạ / thuộc module khác bị bỏ qua."""
        require_aware(now)
        applied = 0
        with open_session(self.engine) as session:
            for override in overrides:
                item = session.get(QuizItem, override.item_id)
                if item is None or item.module_id != module_id:
                    continue
                if override.action == "retire":
                    item.retired = True
                    session.add(item)
                    applied += 1
                    continue
                state = session.get(ReviewState, item.id)
                if state is not None:   # câu chưa từng hỏi vốn đã là "mới", không cần reset
                    state.box, state.prev_box, state.due_at = 0, None, now
                    session.add(state)
                    applied += 1
            session.commit()
        return applied
