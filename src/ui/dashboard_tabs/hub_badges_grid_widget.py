"""Lưới huy hiệu: ô 64px (đã mở = ảnh huy hiệu, chưa mở = ảnh _locked), lọc theo nhóm, tiêu đề "Đã có X/N".

Dựng 1 lần theo catalog; `apply()` chỉ đổi trạng thái ô (không dựng lại).
"""

import logging
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.core.gamification.badge_catalog_loader import BADGES_DIR, BadgeDef, load_badge_catalog
from src.core.gamification.hub_snapshot_model import HubSnapshot
from src.core.i18n import i18n, tr

logger = logging.getLogger("ted")
ICON_PX = 64
COLUMNS = 7
ALL = "*"


def _lang_text(texts: dict) -> str:
    return texts.get(i18n.current_language) or texts.get("vi") or next(iter(texts.values()), "")


class _BadgeTile(QFrame):
    def __init__(self, badge: BadgeDef, pix_on: QPixmap, pix_off: QPixmap, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.badge = badge
        self._pix_on, self._pix_off = pix_on, pix_off
        self.setObjectName("BadgeTile")
        self.setFixedWidth(96)
        col = QVBoxLayout(self)
        col.setContentsMargins(6, 8, 6, 8)
        col.setSpacing(4)
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(ICON_PX, ICON_PX)
        self.lbl_icon.setScaledContents(True)
        self.lbl_name = QLabel()
        self.lbl_name.setObjectName("HintLabel")
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setFixedHeight(30)
        col.addWidget(self.lbl_icon, alignment=Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(self.lbl_name)
        self.unlocked = False

    def set_state(self, unlocked: bool, this_week: bool) -> None:
        self.unlocked = unlocked
        self.lbl_icon.setPixmap(self._pix_on if unlocked else self._pix_off)
        self.setProperty("locked", not unlocked)
        self.style().unpolish(self)
        self.style().polish(self)
        name = _lang_text(self.badge.name)
        self.lbl_name.setText(name)
        extra = tr("hub_badge_this_week") if this_week else ("" if unlocked else tr("hub_badge_locked"))
        self.setToolTip(f"{name}\n{_lang_text(self.badge.desc)}" + (f"\n{extra}" if extra else ""))


class HubBadgesGrid(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._snap: Optional[HubSnapshot] = None
        self._tiles: List[_BadgeTile] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        head = QHBoxLayout()
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("SectionLabel")
        self.lbl_owned = QLabel()
        self.lbl_owned.setObjectName("StatusPill")
        self.combo = QComboBox()
        head.addWidget(self.lbl_title)
        head.addWidget(self.lbl_owned)
        head.addStretch(1)
        head.addWidget(self.combo)
        root.addLayout(head)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)
        self.grid.setColumnStretch(COLUMNS, 1)
        root.addWidget(self.grid_host)
        self._build()
        self.combo.currentIndexChanged.connect(lambda *_: self._relayout())

    def _build(self) -> None:
        try:
            catalog = load_badge_catalog()
        except Exception:  # noqa: BLE001 - catalog hỏng: lưới trống, trang Hub vẫn dùng được
            logger.exception("Không đọc được catalog huy hiệu cho Hub")
            return
        locked_pix = self._pixmap(BADGES_DIR / catalog.locked_image)
        for badge in catalog.badges:
            # có parent ngay từ đầu: ô không parent + setVisible(True) sẽ bật 50 cửa sổ top-level chớp lên màn hình
            self._tiles.append(_BadgeTile(badge, self._pixmap(badge.image_path()), locked_pix, self.grid_host))
        self._categories = sorted({t.badge.category for t in self._tiles})
        self._fill_combo()
        self._relayout()

    @staticmethod
    def _pixmap(path) -> QPixmap:
        pix = QPixmap(str(path))
        return pix.scaled(ICON_PX, ICON_PX, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

    def _fill_combo(self) -> None:
        self.combo.blockSignals(True)
        keep = self.combo.currentData() or ALL
        self.combo.clear()
        self.combo.addItem(tr("hub_category_all"), ALL)
        for cat in getattr(self, "_categories", []):
            self.combo.addItem(tr(f"hub_category_{cat}"), cat)
        self.combo.setCurrentIndex(max(0, self.combo.findData(keep)))
        self.combo.blockSignals(False)

    def _relayout(self) -> None:
        """Xếp lại các ô khớp bộ lọc (ô không khớp được ẩn)."""
        wanted = self.combo.currentData() or ALL
        while self.grid.count():
            self.grid.takeAt(0)
        shown = 0
        for tile in self._tiles:
            visible = wanted == ALL or tile.badge.category == wanted
            tile.setVisible(visible)
            if visible:
                self.grid.addWidget(tile, shown // COLUMNS, shown % COLUMNS, Qt.AlignmentFlag.AlignTop)
                shown += 1

    def apply(self, snap: HubSnapshot) -> None:
        self._snap = snap
        owned = 0
        for tile in self._tiles:
            unlocked = tile.badge.id in snap.badges_unlocked
            owned += unlocked
            tile.set_state(unlocked, tile.badge.id in snap.badges_this_week)
        self.lbl_owned.setText(tr("hub_badges_owned", owned=owned, total=len(self._tiles)))
        self.lbl_title.setText(tr("hub_badges_title"))

    def retranslate_ui(self) -> None:
        self._fill_combo()
        if self._snap is not None:
            self.apply(self._snap)
        else:
            self.lbl_title.setText(tr("hub_badges_title"))
