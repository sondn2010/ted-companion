from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from src.core.connection_registry_and_settings_migration import HermesConnection
from src.core.i18n import tr
from src.ui.button_text_escape import btn_text
from src.ui.dashboard_tabs.connection_search_filter import filter_connection_table_rows
from src.ui.dashboard_tabs.hermes_connection_edit_dialog import HermesConnectionEditDialog

COL_NAME, COL_MODEL, COL_URL, COL_STATUS = range(4)


class BrainSelectDialog(QDialog):
    """
    Hộp thoại Chọn Não AI cho module:
    - Tìm kiếm thời gian thực theo tên, model, URL, hoặc ID.
    - Hiển thị thông tin chi tiết từng Não AI và đánh dấu Não AI đang được gán.
    - Cho phép chọn nhanh bằng double-click hoặc nút 'Chọn'.
    - Hỗ trợ nút bỏ chọn (clear) và nút tạo Não AI mới ngay tại chỗ.
    """

    def __init__(
        self,
        connections: list[HermesConnection],
        current_id: Optional[str] = None,
        module_name: str = "",
        can_clear: bool = False,
        config=None,
        pool=None,
        parent=None,
    ):
        super().__init__(parent)
        self._connections = list(connections)
        self._current_id = current_id
        self._module_name = module_name
        self._can_clear = can_clear
        self._config = config
        self._pool = pool
        self.selected_connection_id: Optional[str] = current_id

        self.setWindowTitle(tr("brain_select_dialog_title", module=module_name) if module_name else tr("btn_select_brain"))
        self.setMinimumSize(700, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header: Hướng dẫn & Tìm kiếm
        lbl_hint = QLabel(f"Chọn Não AI phụ trách xử lý trí tuệ cho module <b>{module_name or 'này'}</b>:")
        layout.addWidget(lbl_hint)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(tr("brain_select_search_placeholder"))
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.txt_search, stretch=1)
        layout.addLayout(search_row)

        # Bảng danh sách Não AI
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            tr("col_name"),
            tr("col_model"),
            tr("col_url"),
            tr("col_status"),
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(COL_MODEL, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(COL_URL, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, stretch=1)

        # Thanh nút bấm dưới
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)

        if self._can_clear:
            self.btn_clear = QPushButton(btn_text(f"⚠️ {tr('btn_clear_brain')}"))
            self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_clear.setToolTip("Gỡ bỏ kết nối Não AI khỏi module này")
            self.btn_clear.clicked.connect(self._on_clear_clicked)
            bottom_bar.addWidget(self.btn_clear)

        if self._config is not None:
            self.btn_add_new = QPushButton(btn_text("➕ Tạo Não AI mới..."))
            self.btn_add_new.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_add_new.clicked.connect(self._on_create_new_clicked)
            bottom_bar.addWidget(self.btn_add_new)

        bottom_bar.addStretch()

        self.btn_cancel = QPushButton(btn_text("❌ Hủy bỏ"))
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_cancel)

        self.btn_select = QPushButton(btn_text(f"✔️ {tr('btn_select_brain')}"))
        self.btn_select.setObjectName("PrimaryBtn")
        self.btn_select.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select.clicked.connect(self._on_select_clicked)
        bottom_bar.addWidget(self.btn_select)

        layout.addLayout(bottom_bar)

        self._populate_table()
        self._highlight_current()

    def _populate_table(self):
        self.table.setRowCount(0)
        for conn in self._connections:
            r = self.table.rowCount()
            self.table.insertRow(r)

            is_active = (conn.id == self._current_id)
            status_text = "⭐ Đang dùng" if is_active else ""

            self.table.setItem(r, COL_NAME, QTableWidgetItem(f"🧠 {conn.name}"))
            self.table.setItem(r, COL_MODEL, QTableWidgetItem(conn.model))
            self.table.setItem(r, COL_URL, QTableWidgetItem(conn.base_url))
            self.table.setItem(r, COL_STATUS, QTableWidgetItem(status_text))

            self.table.item(r, COL_NAME).setData(Qt.ItemDataRole.UserRole, conn.id)

    def _highlight_current(self):
        if not self._current_id:
            if self.table.rowCount() > 0:
                self.table.selectRow(0)
            return
        for r in range(self.table.rowCount()):
            item = self.table.item(r, COL_NAME)
            if item and item.data(Qt.ItemDataRole.UserRole) == self._current_id:
                self.table.selectRow(r)
                break

    def _on_search_changed(self, text: str):
        filter_connection_table_rows(self.table, self._connections, text, id_col=COL_NAME)

    def _on_selection_changed(self):
        selected_id = self._selected_id()
        self.btn_select.setEnabled(selected_id is not None)

    def _selected_id(self) -> Optional[str]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, COL_NAME)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_row_double_clicked(self):
        self._on_select_clicked()

    def _on_select_clicked(self):
        chosen_id = self._selected_id()
        if chosen_id:
            self.selected_connection_id = chosen_id
            self.accept()

    def _on_clear_clicked(self):
        self.selected_connection_id = None
        self.accept()

    def _on_create_new_clicked(self):
        if self._config is None:
            return
        taken = frozenset(c.id for c in self._config.connections)
        dialog = HermesConnectionEditDialog(taken_ids=taken, parent=self)
        if dialog.exec() and dialog.result_connection:
            new_conn = dialog.result_connection
            self._config.upsert_connection(new_conn)
            self._config.save()
            self._connections = list(self._config.connections)
            self._current_id = new_conn.id
            self._populate_table()
            self._highlight_current()
            self._on_search_changed(self.txt_search.text())
