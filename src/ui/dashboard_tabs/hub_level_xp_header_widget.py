"""Đầu trang Hub: avatar, "Cấp N / 10 · P%", thanh tiến độ tuần 0–100%, XP hôm nay, cảnh báo thanh sẽ tụt."""

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from src.config import settings
from src.core.gamification.hub_snapshot_model import HubSnapshot
from src.core.gamification.level_progression_engine import DECAY_PCT, MAX_LEVEL, MIN_DAILY_XP
from src.core.i18n import tr
from src.ui.character_gallery_entries_and_images import gallery_pixmap

AVATAR_PX = 72
DECAY_WARNING_HOUR = 18   # sau giờ này mà chưa đủ XP tối thiểu → nhắc


class HubLevelXpHeader(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._snap: Optional[HubSnapshot] = None
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 14, 16, 14)
        row.setSpacing(16)
        self.lbl_avatar = QLabel()
        self.lbl_avatar.setFixedSize(AVATAR_PX, AVATAR_PX)
        self.lbl_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.lbl_avatar)
        col = QVBoxLayout()
        col.setSpacing(6)
        self.lbl_level = QLabel()
        self.lbl_level.setObjectName("HubLevelTitle")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.lbl_balance = QLabel()
        self.lbl_balance.setObjectName("HintLabel")
        self.lbl_today = QLabel()
        self.lbl_today.setObjectName("FieldLabel")
        self.lbl_week = QLabel()
        self.lbl_week.setObjectName("HintLabel")
        self.lbl_warning = QLabel()
        self.lbl_warning.setObjectName("HubWarning")
        self.lbl_warning.setWordWrap(True)
        for w in (self.lbl_level, self.bar, self.lbl_balance, self.lbl_today, self.lbl_week, self.lbl_warning):
            col.addWidget(w)
        row.addLayout(col, stretch=1)

    def apply(self, snap: HubSnapshot, now: Optional[datetime] = None) -> None:
        """Cập nhật từ snapshot (không truy vấn DB). `now` chỉ để test cố định giờ."""
        self._snap = snap
        now = now or datetime.now()
        pixmap = gallery_pixmap(settings.character_skin, "idle", AVATAR_PX, False)
        if pixmap is not None:
            self.lbl_avatar.setPixmap(pixmap)
        pct = int(round(snap.pct))
        self.lbl_level.setText(tr("hub_level_max" if snap.level >= MAX_LEVEL else "hub_level",
                                  level=snap.level, max=MAX_LEVEL, pct=pct))
        self.bar.setValue(max(0, min(100, pct)))
        self.lbl_balance.setText(tr("hub_xp_balance", pct=pct, delta=f"{snap.pct_today_delta:+.0f}%"))
        self.lbl_today.setText(tr("hub_xp_today", xp=snap.xp_today, goal=MIN_DAILY_XP))
        self.lbl_week.setText(tr("hub_week_summary", xp=snap.week_xp, active=snap.active_days,
                                 decay=snap.decay_days, peak=snap.peak_level))
        self.lbl_warning.setText(tr("hub_decay_warning", goal=MIN_DAILY_XP, decay=int(DECAY_PCT)))
        self.lbl_warning.setVisible(snap.xp_today < MIN_DAILY_XP and now.hour >= DECAY_WARNING_HOUR)

    def retranslate_ui(self) -> None:
        if self._snap is not None:
            self.apply(self._snap)
