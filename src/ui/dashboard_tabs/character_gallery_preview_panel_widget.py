"""Khung xem trước nhân vật đang chọn trong Bộ sưu tập: ảnh lớn, điều kiện + tiến độ, 5 trạng thái, nút "Dùng nhân vật này"."""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget

from src.core.character_pack_loader import STATE_IDS
from src.core.i18n import tr
from src.core.unlockable_skin_condition_evaluator import describe_condition
from src.ui.button_text_escape import btn_text
from src.ui.character_gallery_entries_and_images import GalleryEntry, gallery_pixmap

BIG_PX = 180
STATE_PX = 44
PANEL_WIDTH = 290


class CharacterGalleryPreviewPanel(QFrame):
    use_requested = Signal(str)   # character key
    tag_clicked = Signal(str)     # tag name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFixedWidth(PANEL_WIDTH)
        self._entry: Optional[GalleryEntry] = None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        self.scroll.setWidget(content)
        root_layout.addWidget(self.scroll)

        self.lbl_hint = QLabel(tr("gallery_select_hint"))
        self.lbl_hint.setObjectName("HintLabel")
        self.lbl_hint.setWordWrap(True)
        layout.addWidget(self.lbl_hint)

        self.lbl_big = QLabel()
        self.lbl_big.setFixedSize(BIG_PX, BIG_PX)
        self.lbl_big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_big, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.lbl_name = QLabel()
        self.lbl_name.setObjectName("SectionLabel")
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_name.setWordWrap(True)
        layout.addWidget(self.lbl_name)

        self.lbl_title_role = QLabel()
        self.lbl_title_role.setObjectName("FieldLabel")
        self.lbl_title_role.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title_role.setWordWrap(True)
        layout.addWidget(self.lbl_title_role)

        self.lbl_personality = QLabel()
        self.lbl_personality.setObjectName("Chip")
        self.lbl_personality.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_personality.setWordWrap(True)
        layout.addWidget(self.lbl_personality)

        self.lbl_personality_desc = QLabel()
        self.lbl_personality_desc.setObjectName("HintLabel")
        self.lbl_personality_desc.setWordWrap(True)
        self.lbl_personality_desc.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.lbl_personality_desc)

        self.lbl_quote = QLabel()
        self.lbl_quote.setObjectName("HintLabel")
        self.lbl_quote.setWordWrap(True)
        self.lbl_quote.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.lbl_quote)

        self.lbl_tags = QLabel()
        self.lbl_tags.setObjectName("HintLabel")
        self.lbl_tags.setWordWrap(True)
        self.lbl_tags.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_tags)

        self.lbl_condition = QLabel()
        self.lbl_condition.setObjectName("HintLabel")
        self.lbl_condition.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_condition.setWordWrap(True)
        layout.addWidget(self.lbl_condition)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        layout.addWidget(self.bar)

        self._state_images: dict[str, QLabel] = {}
        row = QHBoxLayout()
        row.setSpacing(2)
        for state in STATE_IDS:
            image = QLabel()   # tên trạng thái nằm ở tooltip (panel hẹp, chữ dài bị cắt)
            image.setFixedSize(STATE_PX, STATE_PX)
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(image)
            self._state_images[state] = image
        layout.addLayout(row)

        self.btn_use = QPushButton()
        self.btn_use.setObjectName("PrimaryBtn")
        self.btn_use.clicked.connect(lambda: self._entry and self.use_requested.emit(self._entry.key))
        layout.addWidget(self.btn_use)
        layout.addStretch(1)
        self._show_empty()

    def _show_empty(self) -> None:
        for widget in (self.lbl_big, self.lbl_name, self.lbl_title_role, self.lbl_personality,
                       self.lbl_personality_desc, self.lbl_quote, self.lbl_tags, self.lbl_condition,
                       self.bar, self.btn_use, *self._state_images.values()):
            widget.setVisible(False)
        self.lbl_hint.setVisible(True)

    def show_entry(self, entry: GalleryEntry, locked: bool, current: float, target: float, in_use: bool) -> None:
        self._entry = entry
        self.lbl_hint.setVisible(False)
        for widget in (self.lbl_big, self.lbl_name, self.lbl_condition, self.btn_use,
                       *self._state_images.values()):
            widget.setVisible(True)
        self.lbl_name.setText(("🔒 " if locked else "") + entry.name())

        # Tiêu đề chức danh / vai trò
        if entry.title:
            self.lbl_title_role.setText(f"💼 {entry.title}")
            self.lbl_title_role.setVisible(True)
        else:
            self.lbl_title_role.setVisible(False)

        # Tính cách & mô tả
        if entry.personality_title:
            self.lbl_personality.setText(f"🎭 {entry.personality_title}")
            self.lbl_personality.setVisible(True)
        else:
            self.lbl_personality.setVisible(False)

        if entry.personality_desc:
            self.lbl_personality_desc.setText(f"✨ {entry.personality_desc}")
            self.lbl_personality_desc.setVisible(True)
        else:
            self.lbl_personality_desc.setVisible(False)

        # Câu nói tiêu biểu
        if entry.quote:
            self.lbl_quote.setText(f"💬 \"{entry.quote}\"")
            self.lbl_quote.setVisible(True)
        else:
            self.lbl_quote.setVisible(False)

        # Tags
        if entry.tags:
            self.lbl_tags.setText("🏷️ " + "  ".join(f"#{t}" for t in entry.tags))
            self.lbl_tags.setVisible(True)
        else:
            self.lbl_tags.setVisible(False)

        condition = describe_condition(entry.condition) if entry.condition is not None else tr("skin_cond_free")
        self.lbl_condition.setText(f"{condition} — {tr('gallery_progress', current=int(current), target=int(target))}"
                                   if locked and target > 0 else condition)
        self.bar.setVisible(locked and target > 0)
        self.bar.setRange(0, max(1, int(target)))
        self.bar.setValue(int(min(current, target)))
        big = gallery_pixmap(entry.key, "idle", BIG_PX, locked)
        self.lbl_big.setPixmap(big) if big is not None else self.lbl_big.clear()
        for state in STATE_IDS:
            pixmap = gallery_pixmap(entry.key, state, STATE_PX, locked)
            self._state_images[state].setPixmap(pixmap) if pixmap is not None else self._state_images[state].clear()
            self._state_images[state].setToolTip(tr(f"gallery_state_{state}"))
        self.btn_use.setText(btn_text(tr("gallery_in_use") if in_use else tr("gallery_use_btn")))
        self.btn_use.setEnabled(not locked and not in_use)
