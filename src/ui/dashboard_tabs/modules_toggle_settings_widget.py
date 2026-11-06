from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)
from src.core.i18n import tr
from src.ui.button_text_escape import btn_text
from src.ui.dashboard_tabs.brain_select_dialog import BrainSelectDialog
from src.ui.dashboard_tabs.openai_connections_manage_dialog import OpenAIConnectionsManageDialog, HermesConnectionsManageDialog


class ModulesToggleSettingsWidget(QWidget):
    """Mỗi module: bật/tắt, chọn Não AI (qua Dialog tìm kiếm), ⭐ module chính. Quản lý kết nối Não AI."""

    def __init__(self, config, registry, pool=None, parent=None):
        super().__init__(parent)
        self._config, self._registry, self._pool = config, registry, pool
        self._brain_buttons: dict[str, QPushButton] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # Header: Tiêu đề bên trái, Nút 'Quản lý Kết nối tới Não AI' bên phải
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 2)
        header.setSpacing(8)

        self.lbl_title = QLabel(tr("modules_title"))
        self.lbl_title.setObjectName("SectionLabel")
        header.addWidget(self.lbl_title)
        header.addStretch()

        self.btn_manage_connections = QPushButton(f"🧠 {tr('btn_manage_connections')}")
        self.btn_manage_connections.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_manage_connections.setToolTip("Mở hộp thoại quản lý toàn bộ kết nối Não AI (Thêm, Sửa, Nhân bản, Xóa, Test)")
        self.btn_manage_connections.clicked.connect(self._open_manage_connections_dialog)
        header.addWidget(self.btn_manage_connections)

        outer.addLayout(header)

        self._grid_host = QWidget()
        outer.addWidget(self._grid_host)
        self._errors = QLabel()
        self._errors.setWordWrap(True)
        self._errors.setObjectName("ErrorLabel")
        outer.addWidget(self._errors)
        self._group = QButtonGroup(self)
        self.reload()
        # Rebuild trễ 1 nhịp: tín hiệu có thể phát từ chính checkbox/radio đang bị thay thế
        registry.modules_changed.connect(lambda: QTimer.singleShot(0, self.reload))

    def reload(self):
        old = self._grid_host.layout()
        if old is not None:
            QWidget().setLayout(old)  # gỡ layout cũ cùng các widget con
        for btn in self._group.buttons():
            self._group.removeButton(btn)
        self._brain_buttons.clear()

        grid = QGridLayout(self._grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)

        for r, manifest in enumerate(self._registry.all()):
            enabled = self._registry.is_enabled(manifest.id)
            chk = QCheckBox(btn_text(f"{manifest.icon} {manifest.name}".strip()))
            chk.setChecked(enabled)
            chk.toggled.connect(lambda on, mid=manifest.id: self._registry.set_enabled(mid, on))

            conn_id = self._registry.connection_for(manifest.id)
            conn = self._config.get_connection(conn_id) if conn_id else None
            if conn:
                btn_title = f"🧠 {conn.name} ({conn.model})"
                btn_tooltip = f"Não AI đang chọn: {conn.name}\nModel: {conn.model}\nURL: {conn.base_url}\n(Nhấn để chọn Não AI khác)"
            else:
                btn_title = tr("module_no_connection")
                btn_tooltip = "Chưa chọn Não AI. Nhấn để mở danh sách chọn Não AI."

            btn_brain = QPushButton(btn_text(btn_title))
            btn_brain.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_brain.setToolTip(btn_tooltip)
            btn_brain.clicked.connect(lambda _, mid=manifest.id, mname=manifest.name: self._on_pick_brain_clicked(mid, mname))
            self._brain_buttons[manifest.id] = btn_brain

            radio = QRadioButton(tr("radio_active_module"))
            self._group.addButton(radio)
            radio.setEnabled(enabled)
            radio.setChecked(self._registry.active() is not None and self._registry.active().id == manifest.id)
            radio.toggled.connect(lambda on, mid=manifest.id: on and self._registry.set_active(mid))

            grid.addWidget(chk, r, 0)
            grid.addWidget(btn_brain, r, 1)
            grid.addWidget(radio, r, 2)

        errors = self._registry.errors
        self._errors.setText(tr("module_error_prefix") + "\n".join(errors) if errors else "")

    def _open_manage_connections_dialog(self):
        """Mở hộp thoại quản lý toàn bộ các kết nối Não AI."""
        dialog = OpenAIConnectionsManageDialog(self._config, self._pool, self._registry, parent=self)
        dialog.connections_changed.connect(self.reload)
        dialog.exec()
        self.reload()

    def _on_pick_brain_clicked(self, module_id: str, module_name: str):
        """Mở hộp thoại chọn Não AI với ô tìm kiếm."""
        current_id = self._registry.connection_for(module_id)
        manifest = next((m for m in self._registry.all() if m.id == module_id), None)
        can_clear = (manifest.engine != "work") if manifest else True

        dialog = BrainSelectDialog(
            connections=self._config.connections,
            current_id=current_id,
            module_name=module_name,
            can_clear=can_clear,
            config=self._config,
            pool=self._pool,
            parent=self,
        )
        if dialog.exec():
            self._on_connection_picked(module_id, dialog.selected_connection_id)

    def retranslate_ui(self):
        self.lbl_title.setText(tr("modules_title"))
        self.btn_manage_connections.setText(f"🧠 {tr('btn_manage_connections')}")
        self.reload()

    def reload_connections(self):
        """Gọi khi danh sách kết nối đổi (thêm/xoá/nhân bản) để cập nhật hiển thị."""
        self.reload()

    def _on_connection_picked(self, module_id: str, conn_id):
        self._config.set_module_override(module_id, connection=conn_id)
        self._config.save()
        self.reload()
        self._registry.modules_changed.emit()  # engine/badge lấy lại client theo kết nối mới
