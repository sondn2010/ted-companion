"""Logic 1 phiên ôn không phụ thuộc Qt: chấm + ghi Attempt/Leitner, gắn cờ, "Mình đúng mà", gói [TED_EXPLAIN_MISTAKE]."""

import json
import logging
from dataclasses import dataclass

from src.engines.coach.answer_grading import grade_answer
from src.engines.coach.coach_data_models import QuizItem
from src.engines.coach.coach_module_services import CoachModuleServices
from src.engines.coach.coach_request_envelope import envelope
from src.engines.coach.coach_stats_builder import subject_of

logger = logging.getLogger("ted")

EXPLAIN_DISPLAY_TEXT = "Vì sao mình sai câu này?"


@dataclass(frozen=True)
class AnswerResult:
    attempt_id: str
    correct: bool


class CoachQuizSessionService:
    def __init__(self, services: CoachModuleServices):
        self._s = services

    def submit(self, item: QuizItem, user_answer: str, response_secs: int = 0) -> AnswerResult:
        """Chấm theo loại câu rồi ghi Attempt + cập nhật hộp bằng leitner_days của policy hiện tại."""
        correct = grade_answer(item, user_answer)
        attempt, _state = self._s.attempts.record_answer(
            self._s.module_id, item.id, user_answer, correct, response_secs, self._s.now(), self._s.policy().leitner_days)
        return AnswerResult(attempt.id, correct)

    def flag(self, item: QuizItem, reason: str) -> bool:
        return self._s.items.flag_item(item.id, reason.strip() or "(không ghi lý do)")

    def regrade_as_correct(self, attempt_id: str) -> bool:
        """Idempotent: lần 2 trả False (Attempt đã đúng, không cộng hộp thêm)."""
        attempt = self._s.attempts.get_attempt(attempt_id)
        if attempt is None or attempt.correct:
            return False
        self._s.attempts.regrade_as_correct(attempt_id, self._s.now(), self._s.policy().leitner_days)
        return True

    def explain_prompt(self, item: QuizItem, user_answer: str) -> str:
        payload = {
            "learner": self._s.learner_id, "subject": subject_of(item.topic), "topic": item.topic,
            "question": item.question, "choices": json.loads(item.choices_json or "[]"),
            "correct": item.answer, "user_answer": user_answer, "explanation": item.explanation,
        }
        return envelope("TED_EXPLAIN_MISTAKE", payload)

    def ask_tutor(self, item: QuizItem, user_answer: str) -> None:
        """Mở quick chat gắn module, tự gửi yêu cầu giải thích nhưng chỉ hiện nhãn ngắn trong khung chat."""
        self._s.ctx.quick_chat.open_for(
            self._s.module_id, prefill=self.explain_prompt(item, user_answer), auto_send=True,
            display_text=EXPLAIN_DISPLAY_TEXT)
