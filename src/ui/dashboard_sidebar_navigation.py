"""
Sidebar điều hướng + vùng trang cho Dashboard (DESIGN.md: sidebar 256px, thu gọn thành icon rail 64px).

Giữ API con của QTabWidget (addTab/insertTab/removeTab/indexOf/tabText/setTabText/widget/count/
currentWidget/setCurrentWidget/currentIndex/setCurrentIndex/currentChanged) để engine module và test
vẫn gọi `dashboard.tabs.*` như trước.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.ui.theme.design_tokens import SIDEBAR_RAIL_WIDTH, SIDEBAR_WIDTH, SPACE_LG, SPACE_SM
from src.ui.button_text_escape import btn_text


def split_icon_and_label(title: str) -> tuple[str, str]:
    """'✅ Tasks' → ('✅', 'Tasks'). Tiêu đề không có emoji đầu → icon = chữ cái đầu viết hoa."""
    head, _, rest = title.strip().partition(" ")
    if head and rest and not head[0].isalnum():
        return head, rest
    return (title.strip()[:1].upper() or "•"), title.strip()


class SidebarNavigation(QWidget):
    currentChanged = Signal(int)

    def __init__(self, brand_text: str = "Ted", parent=None):
        super().__init__(parent)
        self._titles: list[str] = []
        self._buttons: list[QPushButton] = []
        self._collapsed = False
        self._emitted_index = -1  # chỉ số currentChanged phát gần nhất (tránh phát trùng)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = QFrame(self)
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(SIDEBAR_WIDTH)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(SPACE_SM + 4, SPACE_LG - 4, SPACE_SM + 4, SPACE_SM + 4)
        side.setSpacing(2)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(8, 0, 0, 14)
        self.brand_dot = QLabel("●")
        self.brand_dot.setObjectName("SidebarBrandDot")
        self.brand_label = QLabel(brand_text)
        self.brand_label.setObjectName("SidebarBrand")
        brand_row.addWidget(self.brand_dot)
        brand_row.addWidget(self.brand_label, stretch=1)
        side.addLayout(brand_row)

        self._nav_layout = QVBoxLayout()
        self._nav_layout.setSpacing(2)
        side.addLayout(self._nav_layout)
        side.addStretch(1)

        self.btn_collapse = QPushButton("«")
        self.btn_collapse.setObjectName("NavCollapseBtn")
        self.btn_collapse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_collapse.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        side.addWidget(self.btn_collapse)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        # Trang nằm trong khung có lề gutter-desktop (24px)
        page_host = QWidget(self)
        page_host.setObjectName("PageHost")
        page_layout = QVBoxLayout(page_host)
        page_layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        self.stack = QStackedWidget(page_host)
        self.stack.setObjectName("PageStack")
        self.stack.currentChanged.connect(self._on_stack_changed)
        page_layout.addWidget(self.stack)

        root.addWidget(self.sidebar)
        root.addWidget(page_host, stretch=1)

    # ── API kiểu QTabWidget ──────────────────────────────────────────────
    def addTab(self, widget: QWidget, title: str) -> int:
        return self.insertTab(self.count(), widget, title)

    def insertTab(self, index: int, widget: QWidget, title: str) -> int:
        index = max(0, min(index, self.count()))
        before = self.currentIndex()
        btn = QPushButton(self.sidebar)
        btn.setObjectName("NavItem")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _=False, w=widget: self.setCurrentWidget(w))
        self._group.addButton(btn)
        self._titles.insert(index, title)
        self._buttons.insert(index, btn)
        self._nav_layout.insertWidget(index, btn)
        self.stack.insertWidget(index, widget)
        self._render_button(index)
        self._sync_checked()
        self._emit_if_index_shifted(before)
        return index

    def removeTab(self, index: int) -> None:
        if not 0 <= index < self.count():
            return
        before = self.currentIndex()
        btn = self._buttons.pop(index)
        self._titles.pop(index)
        self._group.removeButton(btn)
        self._nav_layout.removeWidget(btn)  # gỡ ngay để insertTab cùng tick không lệch vị trí
        btn.hide()
        btn.deleteLater()
        self.stack.removeWidget(self.stack.widget(index))
        self._sync_checked()
        self._emit_if_index_shifted(before)

    def indexOf(self, widget: QWidget) -> int:
        return self.stack.indexOf(widget)

    def count(self) -> int:
        return self.stack.count()

    def widget(self, index: int) -> QWidget | None:
        return self.stack.widget(index)

    def tabText(self, index: int) -> str:
        return self._titles[index] if 0 <= index < len(self._titles) else ""

    def setTabText(self, index: int, title: str) -> None:
        if 0 <= index < len(self._titles):
            self._titles[index] = title
            self._render_button(index)

    def currentIndex(self) -> int:
        return self.stack.currentIndex()

    def setCurrentIndex(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

    def currentWidget(self) -> QWidget | None:
        return self.stack.currentWidget()

    def setCurrentWidget(self, widget: QWidget) -> None:
        if self.indexOf(widget) != -1:
            self.stack.setCurrentWidget(widget)

    # ── Thu gọn / hiển thị ───────────────────────────────────────────────
    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.sidebar.setFixedWidth(SIDEBAR_RAIL_WIDTH if collapsed else SIDEBAR_WIDTH)
        self.sidebar.setProperty("collapsed", collapsed)
        self.brand_label.setVisible(not collapsed)
        self.btn_collapse.setText("»" if collapsed else "«")
        for i in range(self.count()):
            self._render_button(i)
        # Repolish cả nút con: selector [collapsed="true"] của cha không tự áp lại cho con
        for w in (self.sidebar, *self._buttons):
            w.style().unpolish(w)
            w.style().polish(w)

    def _render_button(self, index: int) -> None:
        icon, label = split_icon_and_label(self._titles[index])
        btn = self._buttons[index]
        if self._collapsed:
            text = icon
        else:
            # Nhãn dài → "…" thay vì bị cắt giữa chữ. Đo bằng font đậm (mục đang chọn là 600);
            # chiều rộng = sidebar − lề sidebar − padding/viền nút − dư cho glyph emoji dự phòng
            font = QFont(btn.font())
            font.setWeight(QFont.Weight.DemiBold)
            text = QFontMetrics(font).elidedText(f"{icon}  {label}", Qt.TextElideMode.ElideRight, SIDEBAR_WIDTH - 66)
        btn.setText(btn_text(text))
        btn.setToolTip(self._titles[index])  # nhãn dài bị cắt / chế độ rail chỉ còn icon

    def _sync_checked(self) -> None:
        idx = self.currentIndex()
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == idx)

    def _on_stack_changed(self, index: int) -> None:
        self._sync_checked()
        self._emitted_index = index
        self.currentChanged.emit(index)

    def _emit_if_index_shifted(self, before: int) -> None:
        """QStackedWidget dời chỉ số im lặng khi chèn/xoá trang phía trước; QTabWidget thì phát currentChanged."""
        if self.currentIndex() != before and self._emitted_index != self.currentIndex():
            self._emitted_index = self.currentIndex()
            self.currentChanged.emit(self.currentIndex())
