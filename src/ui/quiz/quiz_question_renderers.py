"""Widget hiển thị 1 câu hỏi theo loại (mcq / short / step). Mỗi widget phát `answered(str)` đúng 1 lần
với câu trả lời thô (chữ cái lựa chọn, văn bản gõ, hoặc "Làm được"/"Chưa được" cho step).
Đề, đáp án, gợi ý, lời giải hiển thị được công thức LaTeX / bảng / hình vẽ SVG (rich_content, đã escape an toàn)."""

import json

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from src.engines.coach.coach_data_models import QuizItem
from src.engines.coach.coach_quiz_writing_report_schemas import extract_choice_letter
from src.ui.rich_content.rich_text_view_helpers import rich_choice_button, rich_label, set_rich_text

MAX_HINTS = 3
# Hai nhãn này phải chuẩn hoá (normalize_text) về "lam duoc" / "chua duoc" của answer_grading.grade_step
LABEL_PASS = "Làm được"
LABEL_FAIL = "Chưa được"


def _question_label(text: str) -> QLabel:
    label = rich_label(text, word_wrap=True)
    label.setObjectName("SectionLabel")
    return label


class QuestionWidget(QWidget):
    answered = Signal(str)

    def __init__(self, item: QuizItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.layout_ = QVBoxLayout(self)
        self.layout_.addWidget(_question_label(item.question))
        self._locked = False

    def _emit_once(self, answer: str) -> None:
        if not self._locked:
            self._locked = True
            self.setEnabled(False)
            self.answered.emit(answer)


class McqQuestionWidget(QuestionWidget):
    def __init__(self, item: QuizItem, parent=None):
        super().__init__(item, parent)
        self.choice_buttons: list[QPushButton] = []
        for index, choice in enumerate(json.loads(item.choices_json or "[]")):
            letter = extract_choice_letter(choice) or chr(ord("A") + index)
            button = rich_choice_button(choice)   # chữ thường → QPushButton chuẩn; có công thức → nhãn giàu định dạng
            button.setObjectName("QuizOptionBtn")
            button.clicked.connect(lambda _=False, value=letter: self._emit_once(value))
            self.layout_.addWidget(button)
            self.choice_buttons.append(button)


class ShortQuestionWidget(QuestionWidget):
    def __init__(self, item: QuizItem, parent=None):
        super().__init__(item, parent)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Gõ câu trả lời…")
        self.input.returnPressed.connect(self.submit)
        self.btn_submit = QPushButton("Trả lời")
        self.btn_submit.setObjectName("PrimaryBtn")
        self.btn_submit.clicked.connect(self.submit)
        row.addWidget(self.input, stretch=1)
        row.addWidget(self.btn_submit)
        self.layout_.addLayout(row)

    def submit(self) -> None:
        text = self.input.text().strip()
        if text:
            self._emit_once(text)


class StepQuestionWidget(QuestionWidget):
    """Bài nhiều bước: gợi ý 1/2/3 mở lần lượt, xem lời giải, rồi tự đánh giá."""

    def __init__(self, item: QuizItem, parent=None):
        super().__init__(item, parent)
        self._hints = json.loads(item.hints_json or "[]")[:MAX_HINTS]
        self._revealed = 0
        self.hint_buttons: list[QPushButton] = []
        hint_row = QHBoxLayout()
        for number in range(1, len(self._hints) + 1):
            button = QPushButton(f"Gợi ý {number}")
            button.setEnabled(number == 1)   # chỉ mở theo thứ tự
            button.clicked.connect(self._reveal_next_hint)
            hint_row.addWidget(button)
            self.hint_buttons.append(button)
        self.btn_solution = QPushButton("Xem lời giải")
        self.btn_solution.clicked.connect(self.reveal_solution)
        hint_row.addWidget(self.btn_solution)
        self.layout_.addLayout(hint_row)
        self._revealed_lines: list[str] = []
        self.reveal_label = rich_label("", word_wrap=True)
        self.layout_.addWidget(self.reveal_label)
        assess_row = QHBoxLayout()
        self.btn_pass = QPushButton(LABEL_PASS)
        self.btn_fail = QPushButton(LABEL_FAIL)
        self.btn_pass.setObjectName("PrimaryBtn")
        self.btn_pass.clicked.connect(lambda: self._emit_once(LABEL_PASS))
        self.btn_fail.clicked.connect(lambda: self._emit_once(LABEL_FAIL))
        assess_row.addWidget(self.btn_pass)
        assess_row.addWidget(self.btn_fail)
        self.layout_.addLayout(assess_row)

    def _append(self, text: str) -> None:
        self._revealed_lines.append(text)
        set_rich_text(self.reveal_label, "\n\n".join(self._revealed_lines))

    def _reveal_next_hint(self) -> None:
        if self._revealed >= len(self._hints):
            return
        self._append(f"💡 Gợi ý {self._revealed + 1}: {self._hints[self._revealed]}")
        self.hint_buttons[self._revealed].setEnabled(False)
        self._revealed += 1
        if self._revealed < len(self.hint_buttons):
            self.hint_buttons[self._revealed].setEnabled(True)

    def reveal_solution(self) -> None:
        self._append(f"✅ Lời giải: {self.item.answer}" + (f"\n{self.item.explanation}" if self.item.explanation else ""))
        self.btn_solution.setEnabled(False)


QUESTION_WIDGETS = {"mcq": McqQuestionWidget, "short": ShortQuestionWidget, "step": StepQuestionWidget}


def make_question_widget(item: QuizItem, parent=None) -> QuestionWidget:
    return QUESTION_WIDGETS.get(item.type, ShortQuestionWidget)(item, parent)
