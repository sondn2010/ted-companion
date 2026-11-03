"""Bảng 2x2 của ma trận Eisenhower kiểu poster: 4 ô nền màu, giữa là 2 trục mũi tên trắng 2 đầu có nhãn
KHẨN CẤP ←→ KHÔNG KHẨN CẤP (ngang) và QUAN TRỌNG ↕ KHÔNG QUAN TRỌNG (dọc).

Tiêu đề + gợi ý mỗi ô là chữ chìm vẽ trên nền ô (QuadrantWatermarkCell) để danh sách task phủ trọn ô.
Trục được vẽ trong khe giữa các ô (paintEvent của bảng, nằm dưới các ô con) nên không che task, không chặn kéo-thả.
"""

from typing import Dict

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath
from PySide6.QtWidgets import QFrame, QGridLayout, QWidget

from src.core.i18n import tr
from src.ui.theme import design_tokens as tk

GUTTER = 26          # khe giữa các ô = chỗ vẽ trục
EDGE = 18            # lề ngoài cho đầu mũi tên
SHAFT = 18           # bề dày thân trục (chữ nằm trong)
HEAD_LEN = 16
HEAD_HALF = 13
_GRID_POS = {1: (0, 0), 2: (0, 1), 3: (1, 0), 4: (1, 1)}
AXIS_COLOR = QColor(tk.MATRIX_AXIS)
AXIS_TEXT = QColor(tk.MATRIX_CARD_TEXT)
WATERMARK_TITLE = QColor(255, 255, 255, 95)   # chữ chìm: đủ đọc khi ô trống, không lấn thẻ task
WATERMARK_HINT = QColor(255, 255, 255, 130)


class QuadrantWatermarkCell(QFrame):
    """Ô màu (Q1..Q4): tiêu đề + gợi ý vẽ thành chữ chìm mờ giữa nền ô (không chiếm chỗ) → danh sách task phủ cả ô."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title = ""
        self.hint = ""

    def set_watermark(self, title: str, hint: str) -> None:
        self.title, self.hint = title, hint
        self.setToolTip(f"{title} — {hint}")
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)  # nền màu + bo góc từ QSS
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        area = QRectF(self.rect()).adjusted(16, 0, -16, 0)
        title_font = QFont(tk.FONT_FAMILY, 26, QFont.Weight.Black)
        while title_font.pointSize() > 12 and QFontMetricsF(title_font).horizontalAdvance(self.title) > area.width():
            title_font.setPointSize(title_font.pointSize() - 2)  # ô hẹp → thu chữ cho vừa
        hint_font = QFont(tk.FONT_FAMILY, 10)
        title_h = QFontMetricsF(title_font).height()
        hint_h = QFontMetricsF(hint_font).height() * 2
        top = area.center().y() - (title_h + hint_h) / 2.0
        painter.setPen(WATERMARK_TITLE)
        painter.setFont(title_font)
        painter.drawText(QRectF(area.left(), top, area.width(), title_h), Qt.AlignmentFlag.AlignCenter, self.title)
        painter.setPen(WATERMARK_HINT)
        painter.setFont(hint_font)
        painter.drawText(QRectF(area.left(), top + title_h, area.width(), hint_h),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, self.hint)


class EisenhowerAxesBoard(QWidget):
    def __init__(self, cells: Dict[int, QWidget], parent=None):
        super().__init__(parent)
        self._cells = cells
        grid = QGridLayout(self)
        grid.setContentsMargins(EDGE, EDGE, EDGE, EDGE)
        grid.setSpacing(GUTTER)
        for q, (row, col) in _GRID_POS.items():
            grid.addWidget(cells[q], row, col)
            grid.setRowStretch(row, 1)
            grid.setColumnStretch(col, 1)

    def _axis_centers(self) -> tuple[float, float]:
        q1, q4 = self._cells[1].geometry(), self._cells[4].geometry()
        return (q1.right() + q4.left()) / 2.0 + 0.5, (q1.bottom() + q4.top()) / 2.0 + 0.5

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx, cy = self._axis_centers()
        w, h = float(self.width()), float(self.height())

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(AXIS_COLOR)
        painter.drawPath(_double_arrow(QPointF(2, cy), QPointF(w - 2, cy)))
        painter.drawPath(_double_arrow(QPointF(cx, 2), QPointF(cx, h - 2)))

        font = QFont(tk.FONT_FAMILY, 8, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        painter.setFont(font)
        painter.setPen(AXIS_TEXT)
        half = SHAFT / 2.0
        # Ngang: nhãn ở giữa mỗi nửa trái/phải (tránh chỗ giao với trục dọc)
        painter.drawText(QRectF(HEAD_LEN, cy - half, cx - HEAD_LEN - half, SHAFT),
                         Qt.AlignmentFlag.AlignCenter, tr("matrix_axis_urgent"))
        painter.drawText(QRectF(cx + half, cy - half, w - cx - half - HEAD_LEN, SHAFT),
                         Qt.AlignmentFlag.AlignCenter, tr("matrix_axis_not_urgent"))
        # Dọc: chữ xoay -90°, nửa trên / nửa dưới
        for top, bottom, key in ((HEAD_LEN, cy - half, "matrix_axis_important"),
                                 (cy + half, h - HEAD_LEN, "matrix_axis_not_important")):
            painter.save()
            painter.translate(cx, (top + bottom) / 2.0)
            painter.rotate(-90)
            length = bottom - top
            painter.drawText(QRectF(-length / 2.0, -half, length, SHAFT), Qt.AlignmentFlag.AlignCenter, tr(key))
            painter.restore()


def _double_arrow(start: QPointF, end: QPointF) -> QPainterPath:
    """Thân chữ nhật + 2 đầu tam giác, ngang hoặc dọc (start/end cùng x hoặc cùng y)."""
    path = QPainterPath()
    half = SHAFT / 2.0
    if start.y() == end.y():
        y, x0, x1 = start.y(), start.x(), end.x()
        path.addRect(QRectF(x0 + HEAD_LEN - 1, y - half, x1 - x0 - 2 * HEAD_LEN + 2, SHAFT))
        for tip, base in ((x0, x0 + HEAD_LEN), (x1, x1 - HEAD_LEN)):
            path.moveTo(tip, y)
            path.lineTo(base, y - HEAD_HALF)
            path.lineTo(base, y + HEAD_HALF)
            path.closeSubpath()
    else:
        x, y0, y1 = start.x(), start.y(), end.y()
        path.addRect(QRectF(x - half, y0 + HEAD_LEN - 1, SHAFT, y1 - y0 - 2 * HEAD_LEN + 2))
        for tip, base in ((y0, y0 + HEAD_LEN), (y1, y1 - HEAD_LEN)):
            path.moveTo(x, tip)
            path.lineTo(x - HEAD_HALF, base)
            path.lineTo(x + HEAD_HALF, base)
            path.closeSubpath()
    return path.simplified()
