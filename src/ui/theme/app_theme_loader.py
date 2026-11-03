"""Nạp theme cho QApplication: đăng ký font Be Vietnam Pro đóng gói + ghép các file QSS theo thứ tự tên
(QSS viết `@TOKEN`, thay bằng giá trị design_tokens lúc nạp)."""

import logging
import re

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from src.config import get_resource_path
from src.ui.theme import design_tokens as tk
from src.ui.theme.design_tokens import BODY_MD, FONT_FAMILY

logger = logging.getLogger("ted")

FONTS_DIR = "assets/fonts"
QSS_DIR = "src/ui/theme/qss"
# Be Vietnam Pro không có glyph emoji/ký hiệu → chỉ định font dự phòng (icon nav, tiêu đề tab đều dùng emoji)
EMOJI_FALLBACKS = ["Segoe UI Emoji", "Segoe UI Symbol", "Apple Color Emoji", "Noto Color Emoji", "Segoe UI"]
_TOKEN_REF = re.compile(r"@([A-Z][A-Z0-9_]*)")


def register_bundled_fonts() -> bool:
    """Đăng ký mọi .ttf trong assets/fonts. Trả về True nếu họ font Be Vietnam Pro dùng được."""
    fonts_dir = get_resource_path(FONTS_DIR)
    for ttf in sorted(fonts_dir.glob("*.ttf")) if fonts_dir.is_dir() else []:
        if QFontDatabase.addApplicationFont(str(ttf)) == -1:
            logger.warning("Không nạp được font %s", ttf.name)
    return FONT_FAMILY in QFontDatabase.families()


def resolve_tokens(qss: str) -> str:
    """Thay `@TÊN_TOKEN` bằng giá trị trong design_tokens (một nguồn màu duy nhất). Token lạ giữ nguyên + log."""
    def replace(match: re.Match) -> str:
        value = getattr(tk, match.group(1), None)
        if not isinstance(value, str):
            logger.warning("QSS dùng token không tồn tại: @%s", match.group(1))
            return match.group(0)
        return value
    return _TOKEN_REF.sub(replace, qss)


def build_stylesheet() -> str:
    """Ghép các file *.qss (base trước, rồi theo tên) thành một stylesheet, đã thay token."""
    qss_dir = get_resource_path(QSS_DIR)
    if not qss_dir.is_dir():
        return ""
    files = sorted(qss_dir.glob("*.qss"), key=lambda p: (p.stem != "00-base", p.name))
    return resolve_tokens("\n".join(p.read_text(encoding="utf-8") for p in files))


def apply_app_theme(app: QApplication) -> None:
    if register_bundled_fonts():
        QFont.insertSubstitutions(FONT_FAMILY, EMOJI_FALLBACKS)
        font = QFont(FONT_FAMILY)
        font.setPixelSize(BODY_MD[0] - 1)  # 13px: mật độ desktop, khớp label-md
        app.setFont(font)
    app.setStyleSheet(build_stylesheet())
