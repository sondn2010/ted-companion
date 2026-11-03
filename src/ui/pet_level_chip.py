"""Chip level nhỏ cạnh pet ("Lv6"): theo dõi trạng thái từ Hub + vẽ + hit-test (bấm → mở Hub).

Màu viền: mặc định PRIMARY; vừa lên cấp (≤10 phút) TERTIARY; bị tụt cấp trong hôm nay WARNING.
"""

from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QPainter

from src.ui.pet_theme_color_helpers import qcolor
from src.ui.theme import design_tokens as tk

CHIP_RECT = QRectF(12, 104, 40, 18)   # dưới avatar, bên trái pill đồng hồ (nút Pomodoro nằm x ≥ 154)
LEVEL_UP_GLOW = timedelta(minutes=10)

Chip = Tuple[str, str]   # (chữ "Lv6", trạng thái "normal" | "up" | "down")


class LevelChipTracker:
    """Gom snapshot + level_changed của Hub thành chip duy nhất; `chip` = None khi chưa có snapshot (không vẽ)."""

    def __init__(self) -> None:
        self.level: Optional[int] = None
        self._up_at: Optional[datetime] = None
        self._down_on: Optional[date] = None

    def on_snapshot(self, snap) -> None:
        self.level = snap.level

    def on_level_changed(self, old: int, new: int, now: Optional[datetime] = None) -> None:
        now = now or datetime.now()
        if new > old:
            self._up_at = now
        elif new < old:
            self._down_on = now.date()

    def chip(self, now: Optional[datetime] = None) -> Optional[Chip]:
        if self.level is None:
            return None
        now = now or datetime.now()
        if self._down_on == now.date():
            state = "down"
        elif self._up_at is not None and now - self._up_at <= LEVEL_UP_GLOW:
            state = "up"
        else:
            state = "normal"
        return f"Lv{self.level}", state


def chip_contains(point: QPointF) -> bool:
    return CHIP_RECT.contains(point)


def paint_level_chip(painter: QPainter, chip: Optional[Chip]) -> None:
    """Vẽ chip (None = bỏ qua)."""
    if chip is None:
        return
    text, state = chip
    border = {"up": tk.TERTIARY, "down": tk.WARNING}.get(state, tk.PRIMARY)
    painter.save()
    painter.setBrush(qcolor(tk.SURFACE_OVERLAY, 0.92))
    painter.setPen(qcolor(border))
    painter.drawRoundedRect(CHIP_RECT, 9, 9)
    painter.setPen(qcolor(tk.TEXT))
    painter.setFont(QFont(tk.FONT_FAMILY, 8, QFont.Weight.DemiBold))
    painter.drawText(CHIP_RECT, Qt.AlignmentFlag.AlignCenter, text)
    painter.restore()
