from html import escape

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from src.core.i18n import i18n, tr
from src.ui.button_text_escape import btn_text


def _btn_text(key: str) -> str:
    return btn_text(tr(key))   # '&' trong nhãn nút sẽ thành phím tắt nếu không nhân đôi


class MindfulPingBanner(QFrame):
    """Banner Mindful Check-in trong Quick Chat: 2 nút trả lời 1 chạm, phát signal cho popup xử lý."""

    focused = Signal()
    distracted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_task_title = ""
        self.setObjectName("WarningBanner")   # kiểu khung cảnh báo dùng chung (00-base.qss)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        self.lbl_question = QLabel(tr("ping_question_default"))
        self.lbl_question.setWordWrap(True)
        buttons = QHBoxLayout()
        self.btn_focused = QPushButton(_btn_text("ping_btn_focused"))
        self.btn_focused.setObjectName("PrimaryBtn")
        self.btn_focused.clicked.connect(self.focused)
        self.btn_distracted = QPushButton(_btn_text("ping_btn_distracted"))
        self.btn_distracted.clicked.connect(self.distracted)
        buttons.addWidget(self.btn_focused)
        buttons.addWidget(self.btn_distracted)
        layout.addWidget(self.lbl_question)
        layout.addLayout(buttons)
        self.hide()

        i18n.language_changed.connect(lambda _: self.retranslate_ui())

    def retranslate_ui(self):
        self.btn_focused.setText(_btn_text("ping_btn_focused"))
        self.btn_distracted.setText(_btn_text("ping_btn_distracted"))
        if self._current_task_title:
            self.lbl_question.setText(tr("ping_question_task", task=escape(self._current_task_title)))
        else:
            self.lbl_question.setText(tr("ping_question_default"))

    def ask(self, task_title: str):
        self._current_task_title = task_title
        self.lbl_question.setText(tr("ping_question_task", task=escape(task_title)))
        self.show()
