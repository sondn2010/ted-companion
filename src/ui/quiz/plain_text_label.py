"""QLabel luôn hiển thị văn bản thuần: nội dung do Hermes/người dùng sinh ra không được diễn giải thành rich text (HTML)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


def plain_label(text: str = "", word_wrap: bool = False) -> QLabel:
    label = QLabel()
    label.setTextFormat(Qt.TextFormat.PlainText)   # đặt trước setText để không bị auto-detect
    label.setText(text)
    label.setWordWrap(word_wrap)
    return label
