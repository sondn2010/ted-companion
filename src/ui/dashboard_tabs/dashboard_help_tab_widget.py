from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from src.config import get_resource_path, settings
from src.core.i18n import i18n
from src.ui.dashboard_tabs.dashboard_help_content_en_html import HELP_HTML_EN
from src.ui.dashboard_tabs.dashboard_help_content_vi_html import HELP_HTML_VI
from src.ui.theme.design_tokens import (
    ON_PRIMARY,
    OUTLINE_STRONG,
    PRIMARY,
    PRIMARY_SOFT,
    SECONDARY_SOFT,
    SURFACE_RAISED,
    TEXT,
    WARNING,
)

HELP_HTML = {"vi": HELP_HTML_VI, "en": HELP_HTML_EN}

AUTHOR_NAME = "Son Do"
AUTHOR_EMAIL = "sondn2010@gmail.com"

# CSS cho nội dung Help trong QTextBrowser (rich-text engine không đọc QSS → build từ design tokens).
# Cỡ chữ 14px, giãn dòng 160% và khoảng cách đoạn/mục rộng để dễ đọc, không bị dính sát nhau.
HELP_CSS = f"""
h1 {{ color: {PRIMARY_SOFT}; font-size: 22px; margin-top: 4px; margin-bottom: 14px; }}
h2 {{ color: {PRIMARY_SOFT}; font-size: 18px; margin-top: 30px; margin-bottom: 12px; }}
h3 {{ color: {SECONDARY_SOFT}; font-size: 15px; margin-top: 22px; margin-bottom: 8px; }}
p {{ color: {TEXT}; font-size: 14px; line-height: 160%; margin-top: 0px; margin-bottom: 12px; }}
li {{ color: {TEXT}; font-size: 14px; line-height: 160%; margin-bottom: 8px; }}
ul, ol {{ margin-top: 4px; margin-bottom: 12px; }}
blockquote {{ color: {TEXT}; margin: 12px 0px 16px 16px; }}
code {{ background-color: {SURFACE_RAISED}; color: {PRIMARY_SOFT}; font-family: Consolas, monospace; }}
table {{ border-collapse: collapse; margin-top: 8px; margin-bottom: 18px; }}
th {{ background-color: {SURFACE_RAISED}; color: {PRIMARY_SOFT}; font-size: 14px; border: 1px solid {OUTLINE_STRONG}; text-align: left; }}
td {{ color: {TEXT}; font-size: 14px; line-height: 150%; border: 1px solid {OUTLINE_STRONG}; }}
a {{ color: {PRIMARY}; text-decoration: none; }}
hr {{ margin-top: 18px; margin-bottom: 18px; }}
"""

UI_TEXT = {
    "vi": {
        "title": "Cẩm nang Ted Companion",
        "search": "🔍 Tìm kiếm thuật ngữ (gõ từ cần tra)...",
        "author": "Thông tin tác giả: {name} · Email: {email}",
    },
    "en": {
        "title": "Ted Companion Handbook",
        "search": "🔍 Search terminology...",
        "author": "Author: {name} · Email: {email}",
    },
}


class DashboardHelpTabWidget(QWidget):
    """
    Tab Trợ giúp & Tra cứu thuật ngữ:
    - Nội dung nhúng sẵn trong ứng dụng (HTML), hiển thị theo ngôn ngữ đang chọn (VI / EN).
    - Tìm kiếm từ khoá nhanh với highlight.
    - Chân trang hiển thị thông tin tác giả.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        lang = getattr(settings, "language", "vi")
        self.current_lang = lang if lang in HELP_HTML else "vi"
        self._init_ui()
        self.load_help()
        i18n.language_changed.connect(self.switch_language)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Header: logo ứng dụng + tiêu đề cẩm nang
        header = QHBoxLayout()
        header.setSpacing(10)
        self.lbl_logo = QLabel()
        self.lbl_logo.setObjectName("HelpLogo")
        logo = QPixmap(str(get_resource_path("assets/icons/logo.png")))
        if not logo.isNull():
            self.lbl_logo.setPixmap(logo.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header.addWidget(self.lbl_logo)
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("HelpHeaderTitle")
        header.addWidget(self.lbl_title, stretch=1)
        layout.addLayout(header)

        # Ô tìm kiếm từ khóa
        self.search_input = QLineEdit()
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        layout.addWidget(self.search_input)

        # Khu vực hiển thị nội dung cẩm nang
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.document().setDefaultStyleSheet(HELP_CSS)
        self.text_browser.document().setDocumentMargin(20)
        self.text_browser.setObjectName("HelpBrowser")
        layout.addWidget(self.text_browser, stretch=1)

        # Chân trang: thông tin tác giả
        self.lbl_author = QLabel()
        self.lbl_author.setObjectName("HintLabel")
        self.lbl_author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_author.setOpenExternalLinks(True)
        layout.addWidget(self.lbl_author)

        self._retranslate()

    def _retranslate(self):
        texts = UI_TEXT[self.current_lang]
        self.lbl_title.setText(texts["title"])
        self.search_input.setPlaceholderText(texts["search"])
        email_link = f'<a href="mailto:{AUTHOR_EMAIL}" style="color: {PRIMARY}; text-decoration: none;">{AUTHOR_EMAIL}</a>'
        self.lbl_author.setText(texts["author"].format(name=AUTHOR_NAME, email=email_link))

    def switch_language(self, lang: str):
        if lang not in HELP_HTML:
            return
        self.current_lang = lang
        self._retranslate()
        self.load_help()

    def load_help(self):
        """Hiển thị nội dung cẩm nang theo ngôn ngữ hiện tại; highlight lại nếu đang tìm kiếm."""
        # Nạp lại HTML gốc cũng là cách xoá highlight cũ mà không làm mất định dạng heading/link
        self.text_browser.setHtml(HELP_HTML[self.current_lang])
        if query := self.search_input.text().strip():
            self._highlight_search(query)

    def _on_search_text_changed(self, _text: str):
        self.load_help()

    def _highlight_search(self, query: str):
        """Highlight tất cả từ khóa tìm kiếm và cuộn tới vị trí đầu tiên tìm thấy."""
        doc = self.text_browser.document()

        # Format màu highlight
        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor(WARNING))
        highlight_format.setForeground(QColor(ON_PRIMARY))

        cursor = QTextCursor(doc)
        first_match = None

        while not cursor.isNull() and not cursor.atEnd():
            cursor = doc.find(query, cursor)
            if not cursor.isNull():
                cursor.mergeCharFormat(highlight_format)
                if first_match is None:
                    first_match = QTextCursor(cursor)

        # Cuộn tới kết quả đầu tiên
        if first_match is not None:
            self.text_browser.setTextCursor(first_match)
            self.text_browser.ensureCursorVisible()
