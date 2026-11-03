from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
)
from src.core.i18n import tr
from src.ui.button_text_escape import btn_text
from src.ui.dashboard_tabs.hermes_connections_settings_widget import HermesConnectionsSettingsWidget


class HermesConnectionsManageDialog(QDialog):
    """
    Hộp thoại Quản lý Kết nối tới Não AI (Hermes):
    - Chứa bảng danh sách kết nối cùng các nút Thêm, Nhân bản, Sửa, Xóa, Kiểm tra, Kiểm tra tất cả.
    """

    connections_changed = Signal()

    def __init__(self, config, pool, registry, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dialog_manage_connections_title"))
        self.setMinimumSize(820, 380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.connections_widget = HermesConnectionsSettingsWidget(config, pool, registry, parent=self)
        self.connections_widget.connections_changed.connect(self.connections_changed)
        layout.addWidget(self.connections_widget, stretch=1)

        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()

        self.btn_close = QPushButton(btn_text("Đóng"))
        self.btn_close.setObjectName("PrimaryBtn")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(self.btn_close)

        layout.addLayout(bottom_bar)

    def retranslate_ui(self):
        self.setWindowTitle(tr("dialog_manage_connections_title"))
        self.connections_widget.retranslate_ui()
