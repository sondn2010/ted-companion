"""Kho lượt trả lời: ghi Attempt + cập nhật ReviewState (Leitner), hoàn tác chấm sai, truy vấn cho thống kê."""

from datetime import datetime
from typing import Optional, Sequence

from sqlmodel import col, func, select

from src.engines.coach.coach_data_models import Attempt, QuizItem, ReviewState, open_session
from src.engines.coach.leitner_box_scheduling import MAX_BOX, due_after_box, next_review
from src.engines.coach.utc_aware_datetime_type import require_aware


class CoachAttemptRepository:
    def __init__(self, engine):
        self.engine = engine

    def record_answer(
        self, module_id: str, item_id: str, user_answer: str, correct: bool, response_secs: int,
        now: datetime, leitner_days: Sequence[float],
    ) -> tuple[Attempt, ReviewState]:
        """Ghi Attempt và cập nhật hộp. Lịch cũ không bị tính lại khi policy đổi (chỉ áp từ lần trả lời này)."""
        require_aware(now)
        with open_session(self.engine) as session:
            item = session.get(QuizItem, item_id)
            if item is None or item.module_id != module_id:
                raise LookupError(f"Không có câu hỏi {item_id} trong module {module_id}")
            state = session.get(ReviewState, item_id) or ReviewState(item_id=item_id, box=0, due_at=now)
            outcome = next_review(state.box, state.lapses, correct, now, leitner_days)
            # prev_box lưu để "Mình đúng mà" khôi phục được trạng thái trước khi bị chấm sai (Red Team #15)
            state.prev_box, state.box, state.lapses = state.box, outcome.box, outcome.lapses
            state.due_at, state.last_reviewed_at = outcome.due_at, now
            attempt = Attempt(item_id=item_id, module_id=module_id, answered_at=now, user_answer=user_answer,
                              correct=correct, response_secs=max(0, response_secs))
            session.add_all([state, attempt])
            session.commit()
            return attempt, state

    def regrade_as_correct(self, attempt_id: str, now: datetime, leitner_days: Sequence[float]) -> Optional[ReviewState]:
        """Người học khiếu nại chấm sai: đổi Attempt thành đúng; nếu đó là lần trả lời gần nhất của câu thì
        đặt lại hộp = prev_box+1, lapses-1. Không thao tác lặp (đã đúng → bỏ qua). Trả state mới hoặc None."""
        require_aware(now)
        with open_session(self.engine) as session:
            attempt = session.get(Attempt, attempt_id)
            if attempt is None or attempt.correct:
                return None
            attempt.correct = True
            session.add(attempt)
            state = session.get(ReviewState, attempt.item_id)
            if state is not None and state.last_reviewed_at == attempt.answered_at:
                state.box = min((state.prev_box or 0) + 1, MAX_BOX)
                state.lapses = max(0, state.lapses - 1)
                state.due_at = due_after_box(state.box, now, leitner_days)
                state.prev_box = None
                session.add(state)
            session.commit()
            return state

    def get_attempt(self, attempt_id: str) -> Optional[Attempt]:
        with open_session(self.engine) as session:
            return session.get(Attempt, attempt_id)

    # ---- truy vấn cho thống kê ----
    def attempts_between(self, module_id: str, start: datetime, end: datetime) -> list[Attempt]:
        with open_session(self.engine) as session:
            stmt = select(Attempt).where(Attempt.module_id == module_id, Attempt.answered_at >= require_aware(start),
                                         Attempt.answered_at < require_aware(end)).order_by(Attempt.answered_at)
            return list(session.exec(stmt).all())

    def attempt_times(self, module_id: str) -> list[datetime]:
        with open_session(self.engine) as session:
            return list(session.exec(select(Attempt.answered_at).where(Attempt.module_id == module_id)).all())

    def first_seen_item_ids(self, module_id: str, start: datetime, end: datetime) -> set[str]:
        """Câu có lần trả lời đầu tiên rơi vào [start, end) = "câu mới" của ngày đó."""
        with open_session(self.engine) as session:
            stmt = select(Attempt.item_id).where(Attempt.module_id == module_id).group_by(Attempt.item_id) \
                .having(func.min(Attempt.answered_at) >= start, func.min(Attempt.answered_at) < end)
            return set(session.exec(stmt).all())

    def load_items(self, item_ids: Sequence[str]) -> dict[str, QuizItem]:
        with open_session(self.engine) as session:
            rows = session.exec(select(QuizItem).where(col(QuizItem.id).in_(list(item_ids)))).all()
            return {row.id: row for row in rows}

    def load_states(self, item_ids: Sequence[str]) -> dict[str, ReviewState]:
        with open_session(self.engine) as session:
            rows = session.exec(select(ReviewState).where(col(ReviewState.item_id).in_(list(item_ids)))).all()
            return {row.item_id: row for row in rows}
