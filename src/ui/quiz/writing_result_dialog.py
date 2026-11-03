"""Hiển thị kết quả chấm bài viết: điểm từng tiêu chí, tổng, trình độ, điểm mạnh, lỗi + sửa, đoạn viết lại."""

from html import escape
from typing import Optional

from PySide6.QtWidgets import QDialog, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from src.engines.coach.coach_quiz_writing_report_schemas import WritingGradeResult
from src.ui.theme.design_tokens import ERROR, TERTIARY


def result_to_html(result: WritingGradeResult) -> str:
    level = f" · trình độ ước tính <b>{escape(result.estimated_level)}</b>" if result.estimated_level else ""
    parts = [f"<h3>Tổng điểm: {result.overall:g}/10{level}</h3>"]
    if result.scores:
        parts.append("<p>" + " · ".join(f"{escape(k)}: <b>{v:g}</b>" for k, v in result.scores.items()) + "</p>")
    if result.strengths:
        parts.append("<p><b>👍 Điểm mạnh</b></p><ul>" + "".join(f"<li>{escape(s)}</li>" for s in result.strengths) + "</ul>")
    if result.errors:
        rows = "".join(
            f"<li><s style='color:{ERROR};'>{escape(e.original)}</s> → <b style='color:{TERTIARY};'>{escape(e.fixed)}</b>"
            f"<br><i>{escape(e.why)}</i></li>" for e in result.errors)
        parts.append(f"<p><b>✏️ Lỗi cần sửa</b></p><ul>{rows}</ul>")
    if result.rewrite_paragraph:
        rows = "".join(f"<p><b>{escape(k)}:</b> {escape(v)}</p>" for k, v in result.rewrite_paragraph.items())
        parts.append(f"<p><b>🔁 Đoạn viết lại gợi ý</b></p>{rows}")
    if result.next_focus:
        parts.append("<p><b>🎯 Tập trung tiếp</b>: " + escape("; ".join(result.next_focus)) + "</p>")
    return "".join(parts)


class WritingResultDialog(QDialog):
    def __init__(self, result: WritingGradeResult, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("📝 Kết quả chấm bài viết")
        self.resize(520, 480)
        layout = QVBoxLayout(self)
        self.view = QTextBrowser()
        self.view.setHtml(result_to_html(result))
        layout.addWidget(self.view)
        btn_close = QPushButton("Đóng")
        btn_close.setObjectName("PrimaryBtn")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
