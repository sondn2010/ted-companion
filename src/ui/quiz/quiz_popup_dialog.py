"""Popup phiên ôn: lần lượt từng câu → chấm + ghi Leitner → phản hồi → câu kế. Hoàn tất cả phiên mới gọi on_completed."""

import logging
import time
from typing import Callable, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from src.engines.coach.coach_data_models import QuizItem
from src.engines.coach.coach_quiz_session_service import AnswerResult, CoachQuizSessionService
from src.ui.quiz.quiz_answer_feedback_panel import AnswerFeedbackPanel
from src.ui.quiz.quiz_question_renderers import make_question_widget

logger = logging.getLogger("ted")


class QuizPopupDialog(QDialog):
    def __init__(
        self, items: Sequence[QuizItem], service: CoachQuizSessionService,
        set_mood: Callable[[str], None] = lambda mood: None,
        on_completed: Callable[[int, int], None] = lambda answered, correct: None,
        title: str = "🧠 Ôn nhanh cùng Ted", parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._items, self._service, self._set_mood, self._on_completed = list(items), service, set_mood, on_completed
        self._index = self._answered = self._correct = 0
        self._shown_at = time.monotonic()
        self._completed = False
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(460, 340)
        self._layout = QVBoxLayout(self)
        self.progress_label = QLabel()
        self.progress_label.setObjectName("MutedLabel")
        self._layout.addWidget(self.progress_label)
        self._body: Optional[QWidget] = None
        self._layout.addStretch(1)   # đẩy nội dung câu hỏi/phản hồi lên sát đầu thay vì giãn đều theo chiều dọc
        self._show_question()

    # ---- dựng từng bước ----
    def _swap_body(self, widget: QWidget) -> None:
        if self._body is not None:
            self._layout.removeWidget(self._body)
            self._body.setParent(None)
            self._body.deleteLater()
        self._body = widget
        self._layout.insertWidget(1, widget)   # ngay sau progress_label, trước stretch

    def _show_question(self) -> None:
        if self._index >= len(self._items):
            self._finish()
            return
        item = self._items[self._index]
        self.progress_label.setText(f"Câu {self._index + 1}/{len(self._items)}")
        widget = make_question_widget(item)
        widget.answered.connect(lambda answer, it=item: self._on_answered(it, answer))
        self._swap_body(widget)
        self._shown_at = time.monotonic()

    def _on_answered(self, item: QuizItem, user_answer: str) -> None:
        secs = int(time.monotonic() - self._shown_at)
        try:
            result = self._service.submit(item, user_answer, secs)
        except Exception:
            logger.exception("Không ghi được kết quả câu %s", item.id)
            result = AnswerResult("", False)
        self._answered += 1
        self._correct += int(result.correct)
        if result.correct:
            self._set_mood("CHEER")
        last = self._index + 1 >= len(self._items)
        panel = AnswerFeedbackPanel(item, user_answer, result.correct, last)
        panel.explain_requested.connect(lambda: self._service.ask_tutor(item, user_answer))
        panel.flag_submitted.connect(lambda reason: self._service.flag(item, reason))
        panel.regrade_requested.connect(lambda: self._regrade(result))
        panel.next_requested.connect(self._next)
        self._swap_body(panel)

    def _regrade(self, result: AnswerResult) -> None:
        if result.attempt_id and self._service.regrade_as_correct(result.attempt_id):
            self._correct += 1
            self._set_mood("CHEER")

    def _next(self) -> None:
        self._index += 1
        self._show_question()

    def _finish(self) -> None:
        if self._completed:
            return
        self._completed = True
        self.progress_label.setText("")
        done_label = QLabel(f"🎉 Xong phiên ôn! Đúng {self._correct}/{self._answered} câu.")
        done_label.setObjectName("SuccessLabel")
        self._swap_body(done_label)
        self._on_completed(self._answered, self._correct)
        self.accept()

    @property
    def correct_count(self) -> int:
        return self._correct
