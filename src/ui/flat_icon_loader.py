"""Trình nạp và cache icon vector phẳng (flat icons) từ thư mục assets/icons/flat/."""

from pathlib import Path
from typing import Dict, Tuple

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from src.config import get_resource_path

_ICON_CACHE: Dict[Tuple[str, int], QIcon] = {}


def get_flat_icon(name: str, size: int = 16) -> QIcon:
    """Trả về QIcon sắc nét (hỗ trợ HiDPI 1x & 2x) từ file SVG phẳng trong assets/icons/flat/."""
    cache_key = (name, size)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

    rel_path = f"assets/icons/flat/{name}.svg"
    full_path = get_resource_path(rel_path)
    if not full_path.exists():
        fallback = Path(__file__).resolve().parents[2] / rel_path
        if fallback.exists():
            full_path = fallback

    if not full_path.exists():
        icon = QIcon()
        _ICON_CACHE[cache_key] = icon
        return icon

    renderer = QSvgRenderer(str(full_path))
    if not renderer.isValid():
        icon = QIcon()
        _ICON_CACHE[cache_key] = icon
        return icon

    icon = QIcon()
    for scale in (1, 2):
        px = size * scale
        pix = QPixmap(px, px)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        renderer.render(painter, QRectF(0, 0, px, px))
        painter.end()
        pix.setDevicePixelRatio(scale)
        icon.addPixmap(pix)

    _ICON_CACHE[cache_key] = icon
    return icon
