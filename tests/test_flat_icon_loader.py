"""Kiểm tra loader icon vector phẳng (flat icons) trong assets/icons/flat/."""

from PySide6.QtCore import QSize
from tests.qt_offscreen_app_helper import get_qapp

from src.ui.flat_icon_loader import _ICON_CACHE, get_flat_icon


def test_all_flat_icons_load_valid_qicon():
    get_qapp()
    icon_names = ["break", "meeting", "play", "pause", "stop", "chat", "park", "untangle"]
    for name in icon_names:
        icon = get_flat_icon(name, 16)
        assert not icon.isNull(), f"Icon {name} phải nạp được và không rỗng"


def test_flat_icon_caching():
    get_qapp()
    _ICON_CACHE.clear()
    icon1 = get_flat_icon("break", 16)
    icon2 = get_flat_icon("break", 16)
    assert icon1 is icon2, "Icon đã nạp phải được trả về từ cache"


def test_nonexistent_icon_returns_null_icon_safely():
    get_qapp()
    icon = get_flat_icon("non_existent_icon_xyz_123", 16)
    assert icon.isNull(), "Icon không tồn tại phải trả về QIcon rỗng thay vì raise lỗi"
