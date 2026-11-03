"""Hộp thoại bài nhiều bước (agenda `step`): đề, Gợi ý 1/2/3, Xem lời giải, tự đánh giá → Attempt + Leitner."""

import logging
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from src.engines.coach.coach_data_models import QuizItem
from src.engines.coach.coach_quiz_session_service import CoachQuizSessionService
from src.ui.quiz.quiz_question_renderers import StepQuestionWidget

logger = logging.getLogger("ted")


class StepProblemDialog(QDialog):
    def __init__(
        self, item: QuizItem, service: CoachQuizSessionService,
        on_assessed: Callable[[bool], None] = lambda passed: None,
        set_mood: Callable[[str], None] = lambda mood: None, parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._item, self._service, self._on_assessed, self._set_mood = item, service, on_assessed, set_mood
        self.setWindowTitle("🧩 Bài nhiều bước")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(460, 360)
        layout = QVBoxLayout(self)
        self.step_widget = StepQuestionWidget(item)
        self.step_widget.answered.connect(self._on_self_assessed)
        layout.addWidget(self.step_widget)

    def _on_self_assessed(self, assessment: str) -> None:
        try:
            result = self._service.submit(self._item, assessment)
        except Exception:
            logger.exception("Không ghi được tự đánh giá bài step %s", self._item.id)
            return
        if result.correct:
            self._set_mood("CHEER")
        self._on_assessed(result.correct)
        self.accept()
