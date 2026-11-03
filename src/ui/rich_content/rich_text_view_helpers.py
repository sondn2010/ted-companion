"""Gắn HTML giàu định dạng vào widget Qt: thay đoạn chữ vừa stream bằng bản đã dựng, nhãn/nút ôn tập có công thức."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy

from src.ui.button_text_escape import btn_text
from src.ui.rich_content.rich_reply_html_renderer import reply_body_html, rich_reply_html
from src.ui.rich_content.rich_reply_segment_patterns import has_rich_markup


def _utf16_len(text: str) -> int:
    """Vị trí trong QTextDocument đếm theo UTF-16 (emoji = 2)."""
    return len(text.encode("utf-16-le")) // 2


def replace_trailing_plain_text_with_html(view, raw_text: str, max_width: int = 360) -> bool:
    """Đoạn cuối tài liệu đúng bằng `raw_text` (vừa stream dạng chữ thuần) → thay bằng HTML công thức/bảng/hình.
    Không khớp (có tin khác chen vào sau) thì giữ nguyên chữ thuần, trả False."""
    if not raw_text or not has_rich_markup(raw_text):
        return False
    cursor = view.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    end = cursor.position()
    length = _utf16_len(raw_text)
    if length > end:
        return False
    cursor.setPosition(end - length)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    if cursor.selectedText().replace(" ", "\n") != raw_text.replace("\r\n", "\n"):
        return False
    cursor.insertHtml(rich_reply_html(raw_text, max_width=max_width))
    view.setTextCursor(cursor)
    return True


def rich_label(text: str = "", word_wrap: bool = True, max_width: int = 420) -> QLabel:
    """QLabel hiển thị câu hỏi/lời giải có công thức. Nội dung đã escape trong renderer → an toàn với văn bản AI."""
    label = QLabel()
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setWordWrap(word_wrap)
    label.setProperty("raw_text", text)
    label.setText(reply_body_html(text, max_width=max_width))
    return label


def set_rich_text(label: QLabel, text: str, max_width: int = 420) -> None:
    label.setProperty("raw_text", text)
    label.setText(reply_body_html(text, max_width=max_width))


def rich_choice_button(text: str) -> QPushButton:
    """Nút đáp án: chữ thường giữ QPushButton chuẩn; có công thức thì nhúng QLabel giàu định dạng bên trong."""
    if not has_rich_markup(text):
        return QPushButton(btn_text(text))   # '&' sẽ thành phím tắt nếu không nhân đôi
    button = QPushButton()
    button.setAccessibleName(text)
    label = rich_label(text, word_wrap=True, max_width=360)
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)   # bấm vào nhãn = bấm nút
    layout = QHBoxLayout(button)
    layout.setContentsMargins(12, 6, 12, 6)
    layout.addWidget(label)
    button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
    button.setMinimumHeight(label.sizeHint().height() + 12)
    return button
