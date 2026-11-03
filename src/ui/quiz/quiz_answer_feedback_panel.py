"""Khung phản hồi sau mỗi câu: đúng/sai + giải thích, hỏi gia sư, báo câu sai, "Mình đúng mà", câu kế."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from src.engines.coach.coach_data_models import QuizItem
from src.ui.rich_content.rich_text_view_helpers import rich_label


class AnswerFeedbackPanel(QFrame):
    explain_requested = Signal()
    flag_submitted = Signal(str)       # lý do
    regrade_requested = Signal()
    next_requested = Signal()

    def __init__(self, item: QuizItem, user_answer: str, correct: bool, is_last: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("QuizFeedbackPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        verdict = QLabel("🎉 Đúng rồi!" if correct else "❌ Chưa đúng")
        verdict.setObjectName("SuccessLabel" if correct else "ErrorLabel")   # tertiary cho đúng, error cho sai
        layout.addWidget(verdict)
        detail = [] if correct else [f"Đáp án: {item.answer}"]
        if item.explanation:
            detail.append(item.explanation)
        self.detail_label = rich_label("\n\n".join(detail), word_wrap=True)   # đáp án/giải thích có thể chứa công thức
        layout.addWidget(self.detail_label)

        actions = QHBoxLayout()
        self.btn_explain = QPushButton("Vì sao sai? Hỏi gia sư")
        self.btn_explain.clicked.connect(self.explain_requested)
        self.btn_flag = QPushButton("🚩 Báo câu sai")
        self.btn_flag.clicked.connect(self._show_flag_input)
        self.btn_regrade = QPushButton("Mình đúng mà")
        self.btn_regrade.clicked.connect(self._on_regrade)
        self.btn_next = QPushButton("Xong" if is_last else "Câu tiếp ▶")
        self.btn_next.setObjectName("PrimaryBtn")
        self.btn_next.clicked.connect(self.next_requested)
        if not correct:
            actions.addWidget(self.btn_explain)
        actions.addWidget(self.btn_flag)
        if not correct and item.type == "short":   # chỉ câu trả lời tự do mới bị chấm oan do khác cách viết
            actions.addWidget(self.btn_regrade)
        actions.addStretch(1)
        actions.addWidget(self.btn_next)
        layout.addLayout(actions)

        self.flag_row = QWidget()
        self.flag_row.setObjectName("FlagRow")
        flag_layout = QHBoxLayout(self.flag_row)
        flag_layout.setContentsMargins(0, 0, 0, 0)
        self.flag_input = QLineEdit()
        self.flag_input.setPlaceholderText("Câu này sai ở đâu? (đề lỗi, đáp án sai…)")
        self.flag_input.returnPressed.connect(self._submit_flag)
        btn_send = QPushButton("Gửi")
        btn_send.clicked.connect(self._submit_flag)
        flag_layout.addWidget(self.flag_input, stretch=1)
        flag_layout.addWidget(btn_send)
        self.flag_row.hide()
        layout.addWidget(self.flag_row)

    def _show_flag_input(self) -> None:
        self.flag_row.show()
        self.flag_input.setFocus()

    def _submit_flag(self) -> None:
        self.flag_row.hide()
        self.btn_flag.setEnabled(False)
        self.btn_flag.setText("🚩 Đã báo")
        self.flag_submitted.emit(self.flag_input.text())

    def _on_regrade(self) -> None:
        self.btn_regrade.setEnabled(False)
        self.btn_regrade.setText("✓ Đã ghi nhận")
        self.regrade_requested.emit()
