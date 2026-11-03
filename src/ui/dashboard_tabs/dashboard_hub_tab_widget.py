"""Trang Dashboard "🏆 Hub của Ted": cấp + XP, 6 chỉ số, huy hiệu, nhân vật, nhật ký 12 tuần.

Chỉ đọc HubSnapshot (không truy vấn DB); riêng nút "Đi chơi" ghi qua service.wellbeing. Làm tươi theo
`snapshot_changed`; mở trang thì nhờ service refresh (debounce) để số liệu mới.
"""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from src.core.i18n import i18n, tr
from src.ui.dashboard_tabs.hub_badges_grid_widget import HubBadgesGrid
from src.ui.dashboard_tabs.hub_character_teaser_widget import HubCharacterTeaser
from src.ui.dashboard_tabs.hub_level_xp_header_widget import HubLevelXpHeader
from src.ui.dashboard_tabs.hub_stat_bars_widget import HubStatBars
from src.ui.dashboard_tabs.hub_weekly_log_table_widget import HubWeeklyLogTable

logger = logging.getLogger("ted")


class DashboardHubTab(QWidget):
    gallery_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._service = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("TitleLabel")
        outer.addWidget(self.lbl_title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName("TransparentHost")
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(12)
        self.header = HubLevelXpHeader()
        self.stats = HubStatBars()
        self.badges = HubBadgesGrid()
        self.characters = HubCharacterTeaser()
        self.weekly_log = HubWeeklyLogTable()
        self.sections = (self.header, self.stats, self.badges, self.characters, self.weekly_log)
        for section in self.sections:
            col.addWidget(section)
        col.addStretch(1)
        scroll.setWidget(host)
        outer.addWidget(scroll, stretch=1)
        self.characters.gallery_requested.connect(self.gallery_requested)
        i18n.language_changed.connect(lambda *_: self.retranslate_ui())
        self.retranslate_ui()

    def bind_service(self, service) -> None:
        """Nối GamificationHubService (None → trang trống, không lỗi)."""
        self._service = service
        if service is None:
            return
        self.stats.bind_wellbeing(service.wellbeing, service.request_refresh)
        self.characters.bind_service(service)
        service.snapshot_changed.connect(self.apply)
        if service.current_snapshot is not None:
            self.apply(service.current_snapshot)

    def apply(self, snap) -> None:
        for section in (self.header, self.stats, self.badges, self.weekly_log):
            section.apply(snap)
        self.characters.refresh()

    def on_opened(self) -> None:
        """Gọi khi trang được mở: làm tươi từ snapshot hiện có + nhờ service tính lại."""
        if self._service is None:
            return
        if self._service.current_snapshot is not None:
            self.apply(self._service.current_snapshot)
        self._service.request_refresh()

    def retranslate_ui(self) -> None:
        self.lbl_title.setText(tr("hub_title"))
        for section in self.sections:
            section.retranslate_ui()
