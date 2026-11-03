"""Bảng nhật ký 12 tuần: dòng đầu = tuần đang diễn ra (live từ snapshot), các dòng sau = tuần đã lưu (mới nhất trước)."""

from datetime import date, timedelta
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from src.core.gamification.hub_snapshot_model import HubSnapshot
from src.core.i18n import tr

COLS = ("week", "final", "peak", "xp", "active", "decay", "badges")
ROW_HEIGHT = 32
MAX_ROWS = 12


def week_range_text(week_start: date) -> str:
    """"20/10–26/10" cho tuần bắt đầu thứ Hai `week_start`."""
    end = week_start + timedelta(days=6)
    return f"{week_start:%d/%m}–{end:%d/%m}"


def _arrow(cur: int, prev: Optional[int]) -> str:
    """▲/▼ khi cấp cuối đổi so với tuần cũ hơn liền kề."""
    if prev is None or cur == prev:
        return ""
    return " ▲" if cur > prev else " ▼"


class HubWeeklyLogTable(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._snap: Optional[HubSnapshot] = None
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("SectionLabel")
        root.addWidget(self.lbl_title)
        self.table = QTableWidget(0, len(COLS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table)

    def _rows(self, snap: HubSnapshot) -> List[tuple]:
        """(tuần, cấp cuối, đỉnh, xp, ngày hoạt động, ngày tụt, số huy hiệu) — live trước, tuần đã lưu sau."""
        live = (tr("hub_week_current", range=week_range_text(snap.week_start)), snap.level, snap.peak_level,
                snap.week_xp, snap.active_days, snap.decay_days, len(snap.badges_this_week))
        saved = [(week_range_text(date.fromisoformat(r.week_start)), r.final_level, r.peak_level, r.xp_earned,
                  r.active_days, r.decay_days, len(r.badge_ids))
                 for r in snap.weekly_log if r.week_start != snap.week_start.isoformat()]
        return ([live] + saved)[:MAX_ROWS]

    def apply(self, snap: HubSnapshot) -> None:
        self._snap = snap
        rows = self._rows(snap)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            older = rows[i + 1][1] if i + 1 < len(rows) else None
            for c, value in enumerate(row):
                text = f"{value}{_arrow(value, older)}" if c == 1 else str(value)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignLeft if c == 0 else Qt.AlignmentFlag.AlignHCenter))
                self.table.setItem(i, c, item)
        self.table.setFixedHeight(ROW_HEIGHT * (len(rows) + 1) + 14)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.lbl_title.setText(tr("hub_week_log_title"))
        self.table.setHorizontalHeaderLabels([tr(f"hub_week_col_{c}") for c in COLS])
        if self._snap is not None and self.table.rowCount():
            self.table.item(0, 0).setText(tr("hub_week_current", range=week_range_text(self._snap.week_start)))
