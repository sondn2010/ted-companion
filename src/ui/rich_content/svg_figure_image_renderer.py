"""Vẽ hình minh hoạ SVG (tam giác, trục số, đồ thị, hình học…) do Ted sinh ra thành ảnh PNG nền trắng.

- Nền trắng bo góc như "tấm bảng" → nét vẽ màu đen/đậm của LLM luôn rõ trên giao diện tối.
- QSvgRenderer chỉ vẽ hình tĩnh: không chạy script, không tải tài nguyên ngoài → an toàn với nội dung do AI sinh.
- Ảnh 2x + width/height 1x để nét sắc trên HiDPI; tự thu nhỏ vừa khung chat.
"""

import base64
from functools import lru_cache
from html import escape
import logging
import re
from typing import Optional

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from src.ui.theme import design_tokens as tk

logger = logging.getLogger("ted")

MAX_SVG_CHARS = 200_000
MAX_FIGURE_HEIGHT = 900   # px (1x): SVG khai báo kích thước khổng lồ không được làm treo / tràn RAM
PADDING = 8
_XMLNS_RE = re.compile(r"<svg\b(?![^>]*\bxmlns=)", re.I)
# <image href="file:..."> có thể hiện ảnh trên máy người dùng → chỉ giữ ảnh nhúng data:
_EXTERNAL_IMAGE_RE = re.compile(r"<image\b(?![^>]*\bhref\s*=\s*[\"']data:)[^>]*?(/>|>.*?</image>)", re.I | re.S)


@lru_cache(maxsize=64)
def render_svg_png(svg: str, max_width: int) -> Optional[tuple[bytes, int, int]]:
    """(png 2x, rộng 1x, cao 1x) hoặc None nếu SVG hỏng."""
    if len(svg) > MAX_SVG_CHARS:
        return None
    svg = _XMLNS_RE.sub('<svg xmlns="http://www.w3.org/2000/svg"', svg, count=1)
    svg = _EXTERNAL_IMAGE_RE.sub("", svg)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    if not renderer.isValid():
        return None
    size = renderer.defaultSize()
    width, height = (size.width(), size.height()) if size.width() > 0 and size.height() > 0 else (300, 200)
    inner_max = max(60, max_width - 2 * PADDING)
    if width > inner_max:
        height, width = max(1, round(height * inner_max / width)), inner_max
    if height > MAX_FIGURE_HEIGHT:
        width, height = max(1, round(width * MAX_FIGURE_HEIGHT / height)), MAX_FIGURE_HEIGHT
    out_w, out_h = width + 2 * PADDING, height + 2 * PADDING
    image = QImage(out_w * 2, out_h * 2, QImage.Format.Format_ARGB32)
    if image.isNull():
        return None
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(QRectF(0, 0, out_w * 2, out_h * 2), 16, 16)
        renderer.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        renderer.render(painter, QRectF(PADDING * 2, PADDING * 2, width * 2, height * 2))
    finally:
        painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data), out_w, out_h


def svg_figure_html(svg: str, max_width: int = 340) -> str:
    try:
        rendered = render_svg_png(svg.strip(), max_width)
    except Exception as exc:
        logger.debug("Không vẽ được SVG: %s", exc)
        rendered = None
    if rendered is None:
        return f"<p style='color:{tk.TEXT_MUTED};'><i>(Không hiển thị được hình vẽ)</i></p>"
    png, width, height = rendered
    uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return f"<p align='center'><img src='{uri}' width='{width}' height='{height}' alt='{escape('hình vẽ')}'></p>"
