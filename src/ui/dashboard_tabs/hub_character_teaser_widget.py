"""Thẻ nhân vật trên Hub: "Đã mở X/N nhân vật" + gợi ý nhân vật gần mở nhất (kèm tiến độ) + nút mở Bộ sưu tập."""

import logging
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from src.core.i18n import tr
from src.core.skin_unlock_gate import is_skin_unlocked
from src.core.unlockable_skin_condition_evaluator import describe_condition
from src.ui.button_text_escape import btn_text
from src.ui.character_gallery_entries_and_images import build_gallery_entries

logger = logging.getLogger("ted")


class HubCharacterTeaser(QFrame):
    gallery_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._service = None
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)
        head = QHBoxLayout()
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("SectionLabel")
        self.lbl_summary = QLabel()
        self.lbl_summary.setObjectName("StatusPill")
        self.btn_gallery = QPushButton()
        self.btn_gallery.clicked.connect(self.gallery_requested)
        head.addWidget(self.lbl_title)
        head.addWidget(self.lbl_summary)
        head.addStretch(1)
        head.addWidget(self.btn_gallery)
        root.addLayout(head)
        self.lbl_next = QLabel()
        self.lbl_next.setObjectName("FieldLabel")
        self.lbl_next.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        root.addWidget(self.lbl_next)
        root.addWidget(self.bar)

    def bind_service(self, service) -> None:
        self._service = service

    def _progress_map(self) -> dict:
        try:
            svc = self._service
            return svc.skin_unlocks.progress_map() if svc is not None and svc.skin_unlocks else {}
        except Exception:  # noqa: BLE001 - lỗi tiến độ không làm hỏng trang Hub
            logger.exception("Không lấy được tiến độ mở khoá nhân vật")
            return {}

    def _next_unlock(self, entries: list, progress: dict) -> Optional[tuple]:
        """Nhân vật đang khoá có tỉ lệ tiến độ cao nhất → (entry, hiện tại, mục tiêu)."""
        best = None
        for e in entries:
            if e.condition is None or is_skin_unlocked(e.key):
                continue
            cur, target = progress.get(e.key, (0.0, 1.0))
            ratio = cur / target if target else 0.0
            if best is None or ratio > best[0]:
                best = (ratio, e, cur, target)
        return best[1:] if best else None

    def refresh(self) -> None:
        entries = build_gallery_entries()
        unlocked = sum(1 for e in entries if is_skin_unlocked(e.key))
        self.lbl_summary.setText(tr("gallery_summary", unlocked=unlocked, total=len(entries)))
        nxt = self._next_unlock(entries, self._progress_map())
        if nxt is None:
            self.lbl_next.setText(tr("hub_characters_all_done"))
            self.bar.hide()
            return
        entry, cur, target = nxt
        self.lbl_next.setText(tr("hub_characters_next", name=entry.name(), condition=describe_condition(entry.condition)))
        self.bar.setRange(0, max(1, int(target)))
        self.bar.setValue(int(min(cur, target)))
        self.bar.show()

    def retranslate_ui(self) -> None:
        self.lbl_title.setText(tr("hub_characters_title"))
        self.btn_gallery.setText(btn_text(tr("hub_characters_open_gallery")))
        self.refresh()
