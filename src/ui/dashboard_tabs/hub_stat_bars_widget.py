"""6 chỉ số tích lũy trong tuần (thanh 0–100, thứ Hai = 50) + dòng ghi nhật ký "Đi chơi / gia đình / du lịch" (không XP, trần 3 lần/ngày)."""

from datetime import date, timedelta
from typing import Callable, Dict, Optional

from PySide6.QtWidgets import QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from src.core.gamification.hub_snapshot_model import HubSnapshot
from src.core.gamification.wellbeing_daily_repository import MAX_OUTINGS_PER_DAY
from src.core.i18n import tr
from src.ui.button_text_escape import btn_text

STAT_KEYS = ("energy", "data", "learning", "screen_load", "engagement", "health")
HIGH_LOAD = 70           # tải màn hình ≥ ngưỡng này → thanh đổi tông cảnh báo
OUTING_DAYS_BACK = 7     # hôm nay + 6 ngày trước


class HubStatBars(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._snap: Optional[HubSnapshot] = None
        self._repo = None
        self._on_logged: Callable[[], None] = lambda: None
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("SectionLabel")
        root.addWidget(self.lbl_title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        self._rows: Dict[str, tuple] = {}
        for i, key in enumerate(STAT_KEYS):
            name, bar, value = QLabel(), QProgressBar(), QLabel()
            name.setMinimumWidth(130)
            bar.setObjectName("HubStatBar")
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(10)
            value.setMinimumWidth(32)
            for col, w in enumerate((name, bar, value)):
                grid.addWidget(w, i, col)
            self._rows[key] = (name, bar, value)
        root.addLayout(grid)
        root.addLayout(self._build_outing_row())

    def _build_outing_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self.lbl_day = QLabel()
        self.lbl_day.setObjectName("FieldLabel")
        self.combo_day = QComboBox()
        self.btn_outing = QPushButton()
        self.lbl_outing_status = QLabel()
        self.lbl_outing_status.setObjectName("HintLabel")
        for w in (self.lbl_day, self.combo_day, self.btn_outing, self.lbl_outing_status):
            row.addWidget(w)
        row.addStretch(1)
        self.btn_outing.clicked.connect(self._log_outing)
        self.combo_day.currentIndexChanged.connect(lambda *_: self._refresh_outing_status())
        self._fill_days()
        return row

    def bind_wellbeing(self, repo, on_logged: Callable[[], None]) -> None:
        """repo = WellbeingDailyRepository; on_logged gọi sau khi ghi (Hub refresh để chỉ số Gắn kết cập nhật)."""
        self._repo, self._on_logged = repo, on_logged
        self._refresh_outing_status()

    # ---- đi chơi ----
    def _fill_days(self) -> None:
        keep = self.combo_day.currentIndex()
        self.combo_day.blockSignals(True)
        self.combo_day.clear()
        today = date.today()
        for n in range(OUTING_DAYS_BACK):
            label = tr("hub_outing_day_today") if n == 0 else tr("hub_outing_day_ago", n=n)
            self.combo_day.addItem(label, today - timedelta(days=n))
        self.combo_day.setCurrentIndex(max(0, keep))
        self.combo_day.blockSignals(False)

    def _selected_day(self) -> date:
        return self.combo_day.currentData() or date.today()

    def _refresh_outing_status(self) -> None:
        if self._repo is None:
            self.btn_outing.setEnabled(False)
            self.lbl_outing_status.clear()
            return
        n = self._repo.get(self._selected_day()).outings
        full = n >= MAX_OUTINGS_PER_DAY
        self.btn_outing.setEnabled(not full)
        key = "hub_outing_cap" if full else "hub_outing_logged"
        self.lbl_outing_status.setText(tr(key, n=n, max=MAX_OUTINGS_PER_DAY) if (n or full) else "")

    def _log_outing(self) -> None:
        if self._repo is not None and self._repo.log_outing(self._selected_day()):
            self._on_logged()
        self._refresh_outing_status()

    # ---- hiển thị ----
    def apply(self, snap: HubSnapshot) -> None:
        self._snap = snap
        for key, (name, bar, value) in self._rows.items():
            today = snap.stats.get(key)
            for w in (name, bar, value):
                w.setVisible(today is not None)   # Học tập: None = không có coach → ẩn cả dòng
            if today is None:
                continue
            delta = snap.stats_delta_today.get(key)
            bar.setValue(int(today))
            value.setText(str(int(today)))
            tone = "warn" if key == "screen_load" and today >= HIGH_LOAD else "ok"
            if bar.property("tone") != tone:
                bar.setProperty("tone", tone)
                bar.style().unpolish(bar)
                bar.style().polish(bar)
            tip = tr(f"hub_stat_{key}_tip", delta="—" if delta is None else f"{int(delta):+d}")
            for w in (name, bar, value):
                w.setToolTip(tip)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.lbl_title.setText(tr("hub_stats_title"))
        for key, (name, _bar, _value) in self._rows.items():
            name.setText(tr(f"hub_stat_{key}"))
        self.lbl_day.setText(tr("hub_outing_day_label"))
        self.btn_outing.setText(btn_text(tr("hub_outing_button")))
        self._fill_days()
        self._refresh_outing_status()
