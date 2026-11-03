"""Trang Dashboard "🎭 Nhân vật": lưới nhân vật chia nhóm (có sẵn trước, rồi từng pack), thẻ khoá xám + tiến độ,
bấm thẻ → khung xem 5 trạng thái + nút "Dùng nhân vật này". Hỗ trợ tìm kiếm theo tên, lọc theo tag và hiển thị cá tính.

Dựng lười khi mở lần đầu (42+ ảnh). Tiến độ lấy từ GamificationHubService.skin_unlocks (bind_gamification);
chưa có Hub → mọi nhân vật coi như mở (cùng hành vi cổng skin_unlock_gate).
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.config import settings
from src.core.i18n import i18n, tr
from src.core.skin_unlock_gate import is_skin_unlocked
from src.ui.button_text_escape import btn_text
from src.ui.character_gallery_entries_and_images import BUILTIN_GROUP_ID, GalleryEntry, build_gallery_entries
from src.ui.dashboard_tabs.character_gallery_card_widget import CharacterGalleryCard
from src.ui.dashboard_tabs.character_gallery_preview_panel_widget import CharacterGalleryPreviewPanel

logger = logging.getLogger("ted")
GRID_COLUMNS = 3

THEME_FILTER_TAGS = [
    ("all", "gallery_tag_all", True),
    ("unlocked", "gallery_tag_unlocked", True),
    ("locked", "gallery_tag_locked", True),
    ("Có sẵn", "gallery_tag_builtin", True),
    ("Công sở", "gallery_tag_office", True),
    ("Waifu", "gallery_tag_waifu", True),
    ("Học sinh", "gallery_tag_students", True),
    ("Sinh vật", "gallery_tag_creatures", True),
    ("Việt Nam", "gallery_tag_vietnam", True),
]

PERSONALITY_FILTER_TAGS = [
    ("Vui vẻ", "😄 Vui vẻ"),
    ("Dễ thương", "🌸 Dễ thương"),
    ("Năng động", "⚡ Năng động"),
    ("Điềm tĩnh", "🦉 Điềm tĩnh"),
    ("Kỷ luật", "🎯 Kỷ luật"),
    ("Hài hước", "🤪 Hài hước"),
    ("Dịu dàng", "🌿 Dịu dàng"),
]


class CharacterGalleryTabWidget(QWidget):
    def __init__(self, focus_engine, parent=None):
        super().__init__(parent)
        self.focus_engine = focus_engine
        self._service = None
        self._built = False
        self._cards: dict[str, CharacterGalleryCard] = {}
        self._group_labels: list[tuple[QLabel, GalleryEntry]] = []
        self._group_sections: list[tuple[QLabel, QWidget, list[CharacterGalleryCard]]] = []
        self._selected: Optional[str] = None
        self._selected_tag: str = "all"
        self._tag_buttons: dict[str, QPushButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # Header: tiêu đề + tóm tắt
        head = QHBoxLayout()
        self.lbl_title = QLabel(tr("gallery_title"))
        self.lbl_title.setObjectName("TitleLabel")
        self.lbl_summary = QLabel()
        self.lbl_summary.setObjectName("StatusPill")
        head.addWidget(self.lbl_title)
        head.addWidget(self.lbl_summary)
        head.addStretch(1)
        root.addLayout(head)

        # Thanh tìm kiếm & lọc tags
        filter_box = QVBoxLayout()
        filter_box.setSpacing(6)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(tr("gallery_search_placeholder"))
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.textChanged.connect(self._on_search_changed)
        filter_box.addWidget(self.txt_search)

        # Hàng 1 tags: Chủ đề & Trạng thái mở khoá
        row_themes = QHBoxLayout()
        row_themes.setSpacing(6)
        lbl_theme_prefix = QLabel(tr("gallery_filter_theme_label"))
        lbl_theme_prefix.setObjectName("HintLabel")
        row_themes.addWidget(lbl_theme_prefix)
        self._lbl_theme_prefix = lbl_theme_prefix

        self._tag_group = QButtonGroup(self)
        self._tag_group.setExclusive(False)

        for tag_key, label_val, is_tr in THEME_FILTER_TAGS:
            btn = QPushButton(tr(label_val) if is_tr else label_val)
            btn.setObjectName("GalleryTagBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=tag_key: self._on_tag_button_clicked(k))
            row_themes.addWidget(btn)
            self._tag_buttons[tag_key] = btn
            self._tag_group.addButton(btn)
        row_themes.addStretch(1)
        filter_box.addLayout(row_themes)

        # Hàng 2 tags: Cá tính nhân vật
        row_pers = QHBoxLayout()
        row_pers.setSpacing(6)
        lbl_pers_prefix = QLabel(tr("gallery_filter_personality_label"))
        lbl_pers_prefix.setObjectName("HintLabel")
        row_pers.addWidget(lbl_pers_prefix)
        self._lbl_pers_prefix = lbl_pers_prefix

        for tag_key, label_val in PERSONALITY_FILTER_TAGS:
            btn = QPushButton(label_val)
            btn.setObjectName("GalleryTagBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=tag_key: self._on_tag_button_clicked(k))
            row_pers.addWidget(btn)
            self._tag_buttons[tag_key] = btn
            self._tag_group.addButton(btn)
        row_pers.addStretch(1)
        filter_box.addLayout(row_pers)

        root.addLayout(filter_box)

        # Body: Lưới cuộn bên trái + Khung xem trước bên phải
        body = QHBoxLayout()
        body.setSpacing(16)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid_host = QWidget()
        self.grid_layout = QVBoxLayout(self.grid_host)
        self.grid_layout.setContentsMargins(0, 0, 8, 0)
        self.grid_layout.setSpacing(10)
        self.scroll.setWidget(self.grid_host)
        body.addWidget(self.scroll, stretch=1)

        self.preview = CharacterGalleryPreviewPanel()
        self.preview.use_requested.connect(self._on_use_requested)
        self.preview.tag_clicked.connect(self._on_tag_button_clicked)
        body.addWidget(self.preview)
        root.addLayout(body, stretch=1)

        # Khung thông báo không có kết quả tìm kiếm
        self._empty_container = QWidget()
        empty_layout = QVBoxLayout(self._empty_container)
        empty_layout.setContentsMargins(0, 30, 0, 30)
        empty_layout.setSpacing(10)
        self._empty_label = QLabel(tr("gallery_no_results"))
        self._empty_label.setObjectName("HintLabel")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self._empty_label)
        self.btn_clear_filters = QPushButton(btn_text(tr("gallery_clear_filters")))
        self.btn_clear_filters.setObjectName("SecondaryBtn")
        self.btn_clear_filters.setFixedHeight(30)
        self.btn_clear_filters.clicked.connect(self._clear_filters)
        empty_layout.addWidget(self.btn_clear_filters, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._empty_container.setVisible(False)
        self.grid_layout.addWidget(self._empty_container)

        self._update_tag_buttons_ui()

        focus_engine.character_changed.connect(lambda *_: self.refresh())
        i18n.language_changed.connect(lambda *_: self.retranslate_ui())

    # ---- vòng đời ----
    def bind_gamification(self, service) -> None:
        """Nối Hub service: tiến độ/mở khoá cập nhật theo snapshot_changed (service None → bỏ qua)."""
        self._service = service
        if service is not None:
            service.snapshot_changed.connect(lambda *_: self.refresh())

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def _build(self) -> None:
        self._built = True
        self._cards.clear()
        self._group_labels.clear()
        self._group_sections.clear()
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

        grid: Optional[QGridLayout] = None
        group, count = None, 0
        current_group_cards: list[CharacterGalleryCard] = []
        current_header: Optional[QLabel] = None
        current_grid_host: Optional[QWidget] = None

        for entry in build_gallery_entries():
            if entry.group_id != group or grid is None:
                if current_header is not None and current_grid_host is not None:
                    self._group_sections.append((current_header, current_grid_host, list(current_group_cards)))
                current_group_cards.clear()

                group, count = entry.group_id, 0
                header = QLabel()
                header.setObjectName("SectionLabel")
                self._group_labels.append((header, entry))
                self.grid_layout.addWidget(header)
                header.show()
                grid_host = QWidget()
                grid = QGridLayout(grid_host)
                grid.setContentsMargins(0, 0, 0, 0)
                grid.setSpacing(8)
                self.grid_layout.addWidget(grid_host)
                grid_host.show()
                current_header = header
                current_grid_host = grid_host

            card = CharacterGalleryCard(entry)
            card.clicked.connect(self._on_card_clicked)
            grid.addWidget(card, count // GRID_COLUMNS, count % GRID_COLUMNS,
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            grid.setColumnStretch(GRID_COLUMNS, 1)   # cột đệm cuối hút khoảng trống → thẻ không bị giãn
            card.show()
            self._cards[entry.key] = card
            current_group_cards.append(card)
            count += 1

        if current_header is not None and current_grid_host is not None:
            self._group_sections.append((current_header, current_grid_host, list(current_group_cards)))

        # Khung thông báo rỗng đặt ở cuối grid layout
        self.grid_layout.addWidget(self._empty_container)
        self.grid_layout.addStretch(1)

    # ---- xử lý lọc và tìm kiếm ----
    def _on_search_changed(self, text: str) -> None:
        self._apply_filter()

    def _on_tag_button_clicked(self, tag_key: str) -> None:
        if self._selected_tag == tag_key and tag_key != "all":
            self._selected_tag = "all"
        else:
            self._selected_tag = tag_key
        self._update_tag_buttons_ui()
        self._apply_filter()

    def _update_tag_buttons_ui(self) -> None:
        for k, btn in self._tag_buttons.items():
            btn.setChecked(k == self._selected_tag)

    def _clear_filters(self) -> None:
        self.txt_search.clear()
        self._selected_tag = "all"
        self._update_tag_buttons_ui()
        self._apply_filter()

    def _matches_filter(self, card: CharacterGalleryCard, query: str, selected_tag: str) -> bool:
        entry = card.entry
        # 1. Kiểm tra tag
        if selected_tag != "all":
            if selected_tag == "unlocked":
                if not is_skin_unlocked(entry.key):
                    return False
            elif selected_tag == "locked":
                if is_skin_unlocked(entry.key):
                    return False
            else:
                tag_low = selected_tag.lower()
                matches_tag = (
                    any(tag_low == t.lower() for t in entry.tags)
                    or tag_low == entry.personality_key.lower()
                    or tag_low in entry.personality_title.lower()
                    or tag_low in entry.group_title.lower()
                )
                if not matches_tag:
                    return False

        # 2. Kiểm tra từ khóa tìm kiếm (theo tên, tag, cá tính, v.v.)
        if query:
            q = query.lower()
            name_vi = entry.name_vi.lower()
            name_en = entry.name_en.lower()
            key = entry.key.lower()
            title = entry.title.lower()
            p_title = entry.personality_title.lower()
            p_desc = entry.personality_desc.lower()
            group_title = entry.group_title.lower()
            quote = entry.quote.lower()
            tags_matched = any(q in t.lower() for t in entry.tags)

            if not (
                q in name_vi
                or q in name_en
                or q in key
                or q in title
                or q in p_title
                or q in p_desc
                or q in group_title
                or q in quote
                or tags_matched
            ):
                return False

        return True

    def _apply_filter(self) -> None:
        if not self._built:
            return

        query = self.txt_search.text().strip()
        selected_tag = self._selected_tag
        visible_count = 0
        unlocked_visible = 0

        for card in self._cards.values():
            visible = self._matches_filter(card, query, selected_tag)
            card.setVisible(visible)
            if visible:
                visible_count += 1
                if is_skin_unlocked(card.entry.key):
                    unlocked_visible += 1

        # Ẩn/hiển thị từng nhóm
        for header, grid_host, group_cards in self._group_sections:
            group_has_visible = any(not c.isHidden() for c in group_cards)
            header.setVisible(group_has_visible)
            grid_host.setVisible(group_has_visible)

        # Hiển thị thông báo khi không có kết quả
        self._empty_container.setVisible(visible_count == 0)

        # Cập nhật số lượng
        has_filter = bool(query or selected_tag != "all")
        if has_filter:
            self.lbl_summary.setText(
                tr("gallery_matching_summary", matched=visible_count, total=len(self._cards), unlocked=unlocked_visible)
            )
        else:
            total_unlocked = sum(1 for k in self._cards if is_skin_unlocked(k))
            self.lbl_summary.setText(tr("gallery_summary", unlocked=total_unlocked, total=len(self._cards)))

    # ---- hiển thị ----
    def _progress_map(self) -> dict:
        service = self._service
        try:
            return service.skin_unlocks.progress_map() if service is not None and service.skin_unlocks else {}
        except Exception:  # noqa: BLE001 - gamification lỗi không làm hỏng trang
            logger.exception("Không lấy được tiến độ mở khoá nhân vật")
            return {}

    def refresh(self) -> None:
        if not self._built:
            if not self.isVisible():   # snapshot/đổi nhân vật khi trang chưa từng mở → chưa dựng 42+ thẻ (lười thật)
                return
            self._build()
        progress = self._progress_map()
        for key, card in self._cards.items():
            locked = not is_skin_unlocked(key)
            current, target = progress.get(key, (1.0, 1.0))
            card.apply_status(locked, current, target)
            card.set_selected(key == self._selected)
        for header, entry in self._group_labels:
            header.setText(entry.group_title if entry.group_id != BUILTIN_GROUP_ID else tr("gallery_group_builtin"))

        self._apply_filter()

        if self._selected in self._cards:
            self._show_selected(progress)

    def retranslate_ui(self) -> None:
        self.lbl_title.setText(tr("gallery_title"))
        self.txt_search.setPlaceholderText(tr("gallery_search_placeholder"))
        self._lbl_theme_prefix.setText(tr("gallery_filter_theme_label"))
        self._lbl_pers_prefix.setText(tr("gallery_filter_personality_label"))
        self._empty_label.setText(tr("gallery_no_results"))
        self.btn_clear_filters.setText(btn_text(tr("gallery_clear_filters")))

        # Cập nhật nhãn các nút tag
        for tag_key, label_val, is_tr in THEME_FILTER_TAGS:
            if tag_key in self._tag_buttons:
                self._tag_buttons[tag_key].setText(tr(label_val) if is_tr else label_val)

        if self._built:
            self.refresh()

    def _show_selected(self, progress: Optional[dict] = None) -> None:
        card = self._cards[self._selected]
        current, target = (progress if progress is not None else self._progress_map()).get(self._selected, (1.0, 1.0))
        self.preview.show_entry(card.entry, card.locked, current, target, self._selected == settings.character_skin)

    def _on_card_clicked(self, key: str) -> None:
        self._selected = key
        for k, card in self._cards.items():
            card.set_selected(k == key)
        self._show_selected()

    def select_character(self, key: str) -> None:
        """Mở sẵn trang với nhân vật `key` được chọn (vd. từ bubble 'mở khoá')."""
        if not self._built:
            self._build()
        if key in self._cards:
            # Nếu nhân vật đang bị ẩn bởi bộ lọc → xóa bộ lọc để hiển thị nhân vật
            card = self._cards[key]
            if card.isHidden():
                self._clear_filters()
            self._on_card_clicked(key)

    def _on_use_requested(self, key: str) -> None:
        self.focus_engine.set_character(key)   # cổng khoá nằm ở FocusEngine; character_changed → refresh
        self.refresh()
