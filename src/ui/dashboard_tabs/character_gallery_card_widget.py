"""Thẻ 1 nhân vật trong lưới Bộ sưu tập: ảnh idle (khoá → phủ xám + 🔒), tên, điều kiện, thanh tiến độ."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout

from src.core.i18n import tr
from src.core.unlockable_skin_condition_evaluator import describe_condition
from src.ui.character_gallery_entries_and_images import GalleryEntry, gallery_pixmap

CARD_WIDTH = 130
THUMB_PX = 96


class CharacterGalleryCard(QFrame):
    clicked = Signal(str)   # character key

    def __init__(self, entry: GalleryEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.locked = False
        self.setObjectName("Card")
        self.setFixedWidth(CARD_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        self.lbl_image = QLabel()
        self.lbl_image.setFixedSize(THUMB_PX, THUMB_PX)
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_image, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.lbl_name = QLabel()
        self.lbl_name.setObjectName("FieldLabel")
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setFixedHeight(34)
        layout.addWidget(self.lbl_name)
        self.lbl_personality = QLabel()
        self.lbl_personality.setObjectName("PersonalityChip")
        self.lbl_personality.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_personality.setFixedHeight(20)
        layout.addWidget(self.lbl_personality)
        self.lbl_condition = QLabel()
        self.lbl_condition.setObjectName("HintLabel")
        self.lbl_condition.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_condition.setWordWrap(True)
        self.lbl_condition.setFixedHeight(30)
        layout.addWidget(self.lbl_condition)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        layout.addWidget(self.bar)
        self.set_selected(False)

    def apply_status(self, locked: bool, current: float, target: float) -> None:
        """Cập nhật theo trạng thái mới nhất (gọi lại mỗi lần Hub refresh / đổi ngôn ngữ)."""
        self.locked = locked
        pixmap = gallery_pixmap(self.entry.key, "idle", THUMB_PX, locked)
        if pixmap is not None:
            self.lbl_image.setPixmap(pixmap)
        name = self.entry.name()
        self.lbl_name.setText(f"🔒 {name}" if locked else name)
        self.lbl_personality.setText(self.entry.personality_short())
        self.lbl_personality.setVisible(bool(self.entry.personality_short()))
        condition = self.entry.condition
        text = describe_condition(condition) if condition is not None else tr("skin_cond_free")
        self.lbl_condition.setText(text if locked else f"✓ {text}")
        self.bar.setVisible(locked and target > 0)
        self.bar.setRange(0, max(1, int(target)))
        self.bar.setValue(int(min(current, target)))
        self.bar.setToolTip(tr("gallery_progress", current=int(current), target=int(target)))

        tooltip_lines = [name]
        if self.entry.personality_title:
            tooltip_lines.append(f"🎭 {self.entry.personality_title}")
        if self.entry.personality_desc:
            tooltip_lines.append(f"📝 {self.entry.personality_desc}")
        if self.entry.tags:
            tooltip_lines.append("🏷️ " + " ".join(f"#{t}" for t in self.entry.tags))
        tooltip_lines.append(f"{'🔒' if locked else '✓'} {text}")
        self.setToolTip("\n".join(tooltip_lines))

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)   # viền theo QSS QFrame#Card[selected="true"]
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.entry.key)
        super().mousePressEvent(event)
