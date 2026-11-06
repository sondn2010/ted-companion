import asyncio
from datetime import datetime
import json
from typing import Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid
from src.core.background_task_spawner import spawn_background_task
from src.core.connection_registry_and_settings_migration import OpenAIConnection
from src.core.i18n import tr
from src.ui.dashboard_tabs.connection_search_filter import filter_connection_table_rows
from src.ui.dashboard_tabs.openai_connection_edit_dialog import OpenAIConnectionEditDialog

COL_NAME, COL_URL, COL_MODEL, COL_STATUS = range(4)


class OpenAIConnectionsSettingsWidget(QWidget):
    """
    Bảng kết nối Não AI (Tên, URL, Model, Trạng thái):
    - Thanh công cụ gọn gàng: Thêm, Kiểm tra tất cả, Nhập JSON, Xuất JSON, Xóa.
    - Click phải chuột vào từng bản ghi: Kiểm tra, Sửa, Nhân bản, Xóa.
    - Thao tác Xóa luôn bắt buộc xác nhận (confirmation) trước khi thực hiện.
    """

    connections_changed = Signal()

    def __init__(self, config, pool, registry, parent=None):
        super().__init__(parent)
        self._config, self._pool, self._registry = config, pool, registry
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Header: Tiêu đề bên trái, Các nút thao tác chung gọn gàng bên phải
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 2)
        header.setSpacing(8)

        self.lbl_title = QLabel(tr("hermes_connections_title"))
        self.lbl_title.setObjectName("SectionLabel")
        header.addWidget(self.lbl_title)
        header.addStretch()

        self.btn_add = QPushButton(f"➕ {tr('btn_add')}")
        self.btn_add.setObjectName("PrimaryBtn")
        self.btn_add.setToolTip("Thêm một kết nối Não AI mới (OpenAI / Ollama / vLLM / v.v.)")
        self.btn_add.clicked.connect(self._on_add)

        self.btn_test_all = QPushButton(f"⚡ {tr('btn_test_all')}")
        self.btn_test_all.setToolTip("Kiểm tra một lúc toàn bộ các kết nối Não AI trong danh sách")
        self.btn_test_all.clicked.connect(self._on_test_all)

        self.btn_import = QPushButton(f"📥 {tr('btn_import_json')}")
        self.btn_import.setToolTip("Nhập danh sách kết nối Não AI từ file JSON")
        self.btn_import.clicked.connect(self._on_import_json)

        self.btn_export = QPushButton(f"📤 {tr('btn_export_json')}")
        self.btn_export.setToolTip("Xuất danh sách kết nối Não AI ra file JSON để sao lưu hoặc chuyển máy")
        self.btn_export.clicked.connect(self._on_export_json)

        self.btn_delete = QPushButton(f"🗑️ {tr('btn_delete')}")
        self.btn_delete.setObjectName("DangerBtn")
        self.btn_delete.setToolTip("Xóa kết nối đang chọn (yêu cầu xác nhận)")
        self.btn_delete.clicked.connect(self._on_delete)

        # Các nút thao tác cho từng bản ghi (hỗ trợ gọi từ code/test & menu chuột phải)
        self.btn_clone = QPushButton(f"📋 {tr('btn_duplicate')}")
        self.btn_clone.clicked.connect(self._on_clone)

        self.btn_edit = QPushButton(f"✏️ {tr('btn_edit')}")
        self.btn_edit.clicked.connect(self._on_edit)

        self.btn_test = QPushButton(f"🔌 {tr('btn_test')}")
        self.btn_test.clicked.connect(self._on_test)

        # Thêm các nút thanh công cụ gọn gàng vào header
        for b in (self.btn_add, self.btn_test_all, self.btn_import, self.btn_export, self.btn_delete):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            header.addWidget(b)

        layout.addLayout(header)

        # Thanh tìm kiếm thời gian thực (dùng chung logic với Dialog chọn Não AI)
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(tr("brain_select_search_placeholder"))
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.txt_search)

        # Bảng danh sách kết nối
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            tr("col_name"),
            tr("col_base_url"),
            tr("col_model"),
            tr("col_status"),
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.itemDoubleClicked.connect(lambda _: self._on_edit())

        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(COL_URL, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(COL_MODEL, QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(COL_NAME, 180)
        self.table.setColumnWidth(COL_MODEL, 140)
        self.table.setColumnWidth(COL_STATUS, 160)

        layout.addWidget(self.table)
        self.reload()

    def retranslate_ui(self):
        self.lbl_title.setText(tr("hermes_connections_title"))
        self.btn_add.setText(f"➕ {tr('btn_add')}")
        self.btn_test_all.setText(f"⚡ {tr('btn_test_all')}")
        self.btn_import.setText(f"📥 {tr('btn_import_json')}")
        self.btn_export.setText(f"📤 {tr('btn_export_json')}")
        self.btn_delete.setText(f"🗑️ {tr('btn_delete')}")
        self.btn_clone.setText(f"📋 {tr('btn_duplicate')}")
        self.btn_edit.setText(f"✏️ {tr('btn_edit')}")
        self.btn_test.setText(f"🔌 {tr('btn_test')}")
        self.txt_search.setPlaceholderText(tr("brain_select_search_placeholder"))
        self.table.setHorizontalHeaderLabels([
            tr("col_name"),
            tr("col_base_url"),
            tr("col_model"),
            tr("col_status"),
        ])

    def reload(self):
        self.table.setRowCount(0)
        for row, conn in enumerate(self._config.connections):
            self.table.insertRow(row)
            item_name = QTableWidgetItem(conn.name)
            item_name.setData(Qt.ItemDataRole.UserRole, conn.id)
            self.table.setItem(row, COL_NAME, item_name)
            self.table.setItem(row, COL_URL, QTableWidgetItem(conn.base_url))
            self.table.setItem(row, COL_MODEL, QTableWidgetItem(conn.model))
            item_status = QTableWidgetItem("⚪ Chưa kiểm tra")
            self.table.setItem(row, COL_STATUS, item_status)

        # Áp dụng bộ lọc tìm kiếm hiện tại nếu đang có text
        self._apply_search_filter()

    def _on_search_changed(self, text: str):
        self._apply_search_filter()

    def _apply_search_filter(self):
        filter_connection_table_rows(self.table, self._config.connections, self.txt_search.text())

    def _selected_id(self) -> Optional[str]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, COL_NAME)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _select_id(self, conn_id: str):
        for r in range(self.table.rowCount()):
            if self.table.item(r, COL_NAME).data(Qt.ItemDataRole.UserRole) == conn_id:
                self.table.selectRow(r)
                break

    def _on_context_menu(self, pos: QPoint):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        self.table.selectRow(row)
        conn_id = self.table.item(row, COL_NAME).data(Qt.ItemDataRole.UserRole)
        conn = self._config.get_connection(conn_id)
        if not conn:
            return

        menu = QMenu(self)
        act_test = menu.addAction(f"🔌 {tr('btn_test')}")
        act_test.triggered.connect(self._on_test)

        menu.addSeparator()
        act_edit = menu.addAction(f"✏️ {tr('btn_edit')}")
        act_edit.triggered.connect(self._on_edit)

        act_clone = menu.addAction(f"📋 {tr('btn_duplicate')}")
        act_clone.triggered.connect(self._on_clone)

        menu.addSeparator()
        act_delete = menu.addAction(f"🗑️ {tr('btn_delete')}")
        act_delete.triggered.connect(self._on_delete)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    @staticmethod
    def _next_safe_id(prefix: str, taken_ids: frozenset) -> str:
        if prefix not in taken_ids:
            return prefix
        i = 2
        while f"{prefix}_{i}" in taken_ids:
            i += 1
        return f"{prefix}_{i}"

    def _persist(self):
        self._config.save()
        self.reload()
        self.connections_changed.emit()

    def _on_add(self):
        taken = frozenset(c.id for c in self._config.connections)
        dialog = OpenAIConnectionEditDialog(taken_ids=taken, parent=self)
        if dialog.exec() and dialog.result_connection:
            self._config.upsert_connection(dialog.result_connection)
            self._persist()
            self._select_id(dialog.result_connection.id)

    def _on_clone(self):
        conn_id = self._selected_id()
        if not conn_id:
            QMessageBox.information(self, "Nhân bản kết nối", "Vui lòng chọn một kết nối trong bảng để nhân bản.")
            return
        orig = self._config.get_connection(conn_id)
        if orig is None:
            return
        taken = frozenset(c.id for c in self._config.connections)
        new_id = self._next_safe_id(f"{orig.id}_copy", taken)
        clone_conn = OpenAIConnection(
            id=new_id,
            name=f"{orig.name} (Bản sao)",
            base_url=orig.base_url,
            api_key=orig.api_key,
            model=orig.model,
        )
        dialog = OpenAIConnectionEditDialog(existing=clone_conn, taken_ids=taken, is_clone=True, parent=self)
        if dialog.exec() and dialog.result_connection:
            self._config.upsert_connection(dialog.result_connection)
            self._persist()
            self._select_id(dialog.result_connection.id)

    def _on_edit(self):
        conn = self._config.get_connection(self._selected_id() or "")
        if conn is None:
            return
        dialog = OpenAIConnectionEditDialog(existing=conn, parent=self)
        if dialog.exec() and dialog.result_connection:
            self._config.upsert_connection(dialog.result_connection)
            self._persist()

    def _modules_using(self, conn_id: str) -> list[str]:
        return [m.id for m in self._registry.enabled() if self._registry.connection_for(m.id) == conn_id]

    def _on_delete(self):
        """Xóa kết nối đang chọn — Bắt buộc phải có xác nhận (Confirm) từ người dùng."""
        conn_id = self._selected_id()
        if conn_id is None:
            return
        users = self._modules_using(conn_id)
        if users:
            QMessageBox.warning(
                self,
                "Không xoá được",
                f"Kết nối '{conn_id}' đang được dùng bởi module: {', '.join(users)}.\n"
                "Vui lòng chuyển các module này sang kết nối khác trước khi xóa.",
            )
            return

        if len(self._config.connections) <= 1:
            QMessageBox.warning(
                self,
                "Không thể xóa",
                "Phải giữ lại ít nhất 1 kết nối Não AI để ứng dụng có thể hoạt động.",
            )
            return

        conn = self._config.get_connection(conn_id)
        conn_name = conn.name if conn else conn_id

        # Hộp thoại xác nhận trước khi xóa
        reply = QMessageBox.question(
            self,
            "Xác nhận xóa kết nối Não AI",
            f"Bạn có chắc chắn muốn xóa kết nối Não AI “{conn_name}” (ID: {conn_id}) không?\n\n"
            "Thao tác này sẽ xóa vĩnh viễn và không thể hoàn tác.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        error = self._config.delete_connection(conn_id)
        if error:
            QMessageBox.warning(self, "Không xoá được", error)
            return
        self._pool.drop(conn_id)  # chỉ dọn client của kết nối vừa xoá
        self._persist()

    def _on_test(self):
        conn_id = self._selected_id()
        client = self._pool.get(conn_id) if conn_id else None
        if client is None:
            return
        self._set_status(conn_id, "⏳ Đang kiểm tra...")
        spawn_background_task(self._run_test(client, conn_id), f"openai-test-{conn_id}")

    def _on_test_all(self):
        if not self._config.connections:
            return
        for conn in self._config.connections:
            self._set_status(conn.id, "⏳ Đang kiểm tra...")
        self.btn_test_all.setEnabled(False)
        spawn_background_task(self._run_test_all(), "openai-test-all")

    async def _run_test_all(self):
        tasks = []
        for conn in self._config.connections:
            client = self._pool.get(conn.id)
            if client:
                tasks.append(self._run_test(client, conn.id))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if isValid(self):
            self.btn_test_all.setEnabled(True)

    async def _run_test(self, client, conn_id: str):
        try:
            ok, message = await client.ping()  # message đã được client che API key
            if isValid(self):
                self._set_status(conn_id, f"{'✅' if ok else '❌'} {message}")
        except Exception as exc:
            if isValid(self):
                self._set_status(conn_id, f"❌ {exc}")

    def _set_status(self, conn_id: str, text: str):
        for r in range(self.table.rowCount()):
            if self.table.item(r, COL_NAME).data(Qt.ItemDataRole.UserRole) == conn_id:
                self.table.item(r, COL_STATUS).setText(text)
                self.table.item(r, COL_STATUS).setToolTip(text)

    def _on_export_json(self):
        """Xuất danh sách kết nối Não AI ra file JSON."""
        if not self._config.connections:
            QMessageBox.information(self, "Xuất JSON", "Không có kết nối Não AI nào để xuất.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Xuất danh sách Não AI ra file JSON",
            "ted_ai_brains.json",
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return

        data = {
            "app": "Ted Companion",
            "version": 1,
            "exported_at": datetime.now().isoformat(),
            "connections": [c.model_dump() for c in self._config.connections],
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(
                self,
                "Xuất thành công",
                f"Đã xuất thành công {len(self._config.connections)} kết nối Não AI ra file:\n{path}",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi khi xuất file", f"Không thể ghi file:\n{exc}")

    def _on_import_json(self):
        """Nhập danh sách kết nối Não AI từ file JSON."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Nhập danh sách Não AI từ file JSON",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi đọc file", f"Không thể đọc file JSON:\n{exc}")
            return

        # Hỗ trợ dạng list [...] hoặc dict {"connections": [...]} hoặc dict đơn lẻ
        if isinstance(raw_data, list):
            items = raw_data
        elif isinstance(raw_data, dict) and "connections" in raw_data and isinstance(raw_data["connections"], list):
            items = raw_data["connections"]
        elif isinstance(raw_data, dict) and "id" in raw_data and "base_url" in raw_data:
            items = [raw_data]
        else:
            QMessageBox.warning(self, "Định dạng không hợp lệ", "File JSON không chứa danh sách kết nối Não AI hợp lệ.")
            return

        valid_conns = []
        for idx, item in enumerate(items, 1):
            try:
                c = OpenAIConnection.model_validate(item)
                valid_conns.append(c)
            except Exception as exc:
                QMessageBox.warning(self, "Dữ liệu kết nối lỗi", f"Bản ghi #{idx} trong file không hợp lệ:\n{exc}")
                return

        if not valid_conns:
            QMessageBox.information(self, "Thông báo", "Không tìm thấy kết nối nào hợp lệ trong file.")
            return

        existing_ids = {c.id for c in self._config.connections}
        conflicts = [c for c in valid_conns if c.id in existing_ids]

        overwrite = True
        if conflicts:
            reply = QMessageBox.question(
                self,
                "Trùng mã ID kết nối",
                f"Phát hiện {len(conflicts)} kết nối có ID trùng với kết nối hiện tại:\n"
                f"({', '.join(c.id for c in conflicts[:3])}{'...' if len(conflicts) > 3 else ''})\n\n"
                "• Nhấn 'Yes' để GHI ĐÈ các kết nối trùng.\n"
                "• Nhấn 'No' để TỰ ĐỘNG ĐỔI ID và giữ cả hai.\n"
                "• Nhấn 'Cancel' để HỦY BỎ thao tác nhập.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            overwrite = (reply == QMessageBox.StandardButton.Yes)

        taken = set(existing_ids)
        count = 0
        for c in valid_conns:
            if c.id in existing_ids and not overwrite:
                new_id = self._next_safe_id(f"{c.id}_imported", frozenset(taken))
                c = OpenAIConnection(
                    id=new_id,
                    name=f"{c.name} (Nhập)",
                    base_url=c.base_url,
                    api_key=c.api_key,
                    model=c.model,
                )
            taken.add(c.id)
            self._config.upsert_connection(c)
            count += 1

        self._persist()
        QMessageBox.information(
            self,
            "Nhập thành công",
            f"Đã nhập thành công {count} kết nối Não AI vào ứng dụng.",
        )


# Backward compatibility alias
HermesConnectionsSettingsWidget = OpenAIConnectionsSettingsWidget
