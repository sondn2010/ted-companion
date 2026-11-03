from typing import Optional

from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid
from src.core.background_task_spawner import spawn_background_task
from src.core.connection_registry_and_settings_migration import (
    DEFAULT_MODEL_NAME,
    HermesConnection,
    validation_error_summary,
)
from src.ui.button_text_escape import btn_text
from src.ui.dashboard_tabs.hermes_connection_help_panel_html import HELP_PANEL_HTML


class HermesConnectionEditDialog(QDialog):
    """
    Hộp thoại Thêm/Sửa/Nhân bản kết nối Não AI (Hermes):
    - Giao diện 2 cột: Cột trái form nhập liệu có prefill mẫu, cột phải cẩm nang giải thích từng tham số.
    - Hỗ trợ nút Kiểm tra kết nối trực tiếp trong hộp thoại.
    - Validate bằng HermesConnection; API key có nút bật/tắt ẩn hiện.
    """

    def __init__(
        self,
        existing: Optional[HermesConnection] = None,
        taken_ids: frozenset = frozenset(),
        is_clone: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        if is_clone:
            self.setWindowTitle("Nhân bản kết nối Não AI")
        elif existing:
            self.setWindowTitle("Sửa kết nối Não AI")
        else:
            self.setWindowTitle("Thêm kết nối Não AI")

        self.setMinimumSize(850, 580)
        self._taken_ids = taken_ids
        self._is_editing = existing is not None and not is_clone
        self._is_clone = is_clone
        self.result_connection: Optional[HermesConnection] = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header bar: Mẫu điền nhanh (nếu thêm mới) hoặc thông báo sửa / nhân bản
        if not existing and not is_clone:
            tpl_box = QFrame()
            tpl_box.setObjectName("InfoPanel")
            tpl_layout = QHBoxLayout(tpl_box)
            tpl_layout.setContentsMargins(12, 8, 12, 8)
            tpl_layout.setSpacing(8)

            lbl_tpl = QLabel("💡 <b>Mẫu cấu hình nhanh:</b>")
            lbl_tpl.setObjectName("MutedLabel")
            tpl_layout.addWidget(lbl_tpl)

            btn_vps = QPushButton(btn_text("☁️ Mẫu Não AI VPS Cloud (24/7 - Khuyên dùng)"))
            btn_vps.clicked.connect(lambda: self._apply_template("vps"))
            btn_local = QPushButton(btn_text("💻 Mẫu Não AI Local (Offline 127.0.0.1)"))
            btn_local.clicked.connect(lambda: self._apply_template("local"))
            btn_clear = QPushButton(btn_text("🔄 Xóa trắng"))
            btn_clear.setObjectName("GhostBtn")
            btn_clear.clicked.connect(self._clear_fields)
            for tpl_btn in (btn_vps, btn_local, btn_clear):
                tpl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                tpl_layout.addWidget(tpl_btn)

            tpl_layout.addStretch()
            main_layout.addWidget(tpl_box)
        elif is_clone and existing:
            lbl_clone_info = QLabel(f"📋 Đang nhân bản từ kết nối: <b>{existing.name}</b> (sửa lại ID & thông tin nếu cần)")
            lbl_clone_info.setObjectName("SectionLabel")
            main_layout.addWidget(lbl_clone_info)
        else:
            lbl_edit_info = QLabel(f"✏️ Đang chỉnh sửa cấu hình kết nối: <b>{existing.name}</b> (ID: <code>{existing.id}</code>)")
            lbl_edit_info.setObjectName("SectionLabel")
            main_layout.addWidget(lbl_edit_info)

        # Body: 2 cột (Cột trái: Form nhập liệu trong Card; Cột phải: Hướng dẫn chi tiết)
        body_layout = QHBoxLayout()
        body_layout.setSpacing(16)

        form_container = QFrame()
        form_container.setObjectName("Card")
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(20, 16, 20, 16)
        form_layout.setSpacing(6)

        # Field 1: ID
        self.input_id = QLineEdit(existing.id if existing else "")
        self.input_id.setPlaceholderText("vd: work, thcs, vps_cloud (a-z, 0-9, - _)")
        self.input_id.setReadOnly(self._is_editing)
        self._add_field(form_layout, "Mã định danh kết nối (ID):", self.input_id,
                        "Mã duy nhất nội bộ, không có dấu cách; không thể đổi sau khi tạo.")

        # Field 2: Tên hiển thị
        self.input_name = QLineEdit(existing.name if existing else "")
        self.input_name.setPlaceholderText("vd: Não AI VPS Công việc, Não AI Cấp 2 của con")
        self._add_field(form_layout, "Tên kết nối (Display Name):", self.input_name,
                        "Tên thân thiện xuất hiện trên danh sách lựa chọn của các Module.")

        # Field 3: Base URL
        self.input_url = QLineEdit(existing.base_url if existing else "")
        self.input_url.setPlaceholderText("http://100.x.y.z:8080/v1 hoặc http://127.0.0.1:8000/v1")
        self._add_field(form_layout, "Địa chỉ máy chủ (Base URL):", self.input_url,
                        "Bắt buộc bắt đầu bằng http:// hoặc https:// và kết thúc bằng /v1.")

        # Field 4: API Key (có toggle hiện/ẩn)
        key_row = QHBoxLayout()
        key_row.setSpacing(4)
        self.input_key = QLineEdit(existing.api_key if existing else "")
        self.input_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_key.setPlaceholderText("Điền API_SERVER_KEY từ file .env trên VPS")
        self.btn_toggle_key = QPushButton("👁️")
        self.btn_toggle_key.setObjectName("IconBtn")
        self.btn_toggle_key.setToolTip("Hiện / Ẩn API Key")
        self.btn_toggle_key.setFixedWidth(36)
        self.btn_toggle_key.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_key.clicked.connect(self._toggle_key_visibility)
        key_row.addWidget(self.input_key, stretch=1)
        key_row.addWidget(self.btn_toggle_key)
        self._add_field(form_layout, "Khóa xác thực bí mật (API Key):", key_row,
                        "Mã bảo vệ kết nối. Để trống nếu chạy máy Local không đặt mật khẩu.")

        # Field 5: Model
        self.input_model = QLineEdit(existing.model if existing else DEFAULT_MODEL_NAME)
        self.input_model.setPlaceholderText("google/gemini-2.5-flash hoặc qwen-2.5-coder")
        self._add_field(form_layout, "Mô hình AI suy luận (Model ID):", self.input_model,
                        "Định danh mô hình AI; để mặc định nếu bạn dùng cấu hình chuẩn.")

        form_layout.addStretch()
        body_layout.addWidget(form_container, stretch=3)

        # CỘT PHẢI: Panel Hướng Dẫn Chi Tiết
        help_frame = QFrame()
        help_frame.setObjectName("InfoPanel")
        help_layout = QVBoxLayout(help_frame)
        help_layout.setContentsMargins(12, 12, 12, 12)

        self.help_browser = QTextBrowser()
        self.help_browser.setObjectName("TransparentBrowser")
        self.help_browser.setOpenExternalLinks(True)
        self.help_browser.setHtml(HELP_PANEL_HTML)
        help_layout.addWidget(self.help_browser)

        body_layout.addWidget(help_frame, stretch=2)
        main_layout.addLayout(body_layout, stretch=1)

        # Thanh nút bấm dưới: Kiểm tra kết nối + Trạng thái bên trái, Hủy/Lưu bên phải
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)

        self.btn_test = QPushButton(btn_text("🔌 Kiểm tra kết nối"))
        self.btn_test.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test.setToolTip("Kiểm tra kết nối mạng tới máy chủ với thông tin đang nhập")
        self.btn_test.clicked.connect(self._on_test_clicked)
        bottom_bar.addWidget(self.btn_test)

        self.lbl_test_status = QLabel("")
        self.lbl_test_status.setObjectName("MutedLabel")
        bottom_bar.addWidget(self.lbl_test_status)

        bottom_bar.addStretch()

        self.btn_cancel = QPushButton(btn_text("❌ Hủy bỏ"))
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_cancel)

        self.btn_save = QPushButton(btn_text("💾 Lưu kết nối"))
        self.btn_save.setObjectName("PrimaryBtn")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._on_accept)
        bottom_bar.addWidget(self.btn_save)

        main_layout.addLayout(bottom_bar)

        # Mặc định prefill mẫu VPS nếu thêm mới hoàn toàn
        if not existing and not is_clone:
            self._apply_template("vps")

    @staticmethod
    def _add_field(form_layout: QVBoxLayout, label: str, field, hint: str) -> None:
        """Một nhóm field: FieldLabel + ô nhập (widget hoặc layout) + HintLabel."""
        lbl = QLabel(label)
        lbl.setObjectName("FieldLabel")
        form_layout.addWidget(lbl)
        if isinstance(field, QWidget):
            form_layout.addWidget(field)
        else:
            form_layout.addLayout(field)
        lbl_hint = QLabel(hint)
        lbl_hint.setObjectName("HintLabel")
        form_layout.addWidget(lbl_hint)
        form_layout.addSpacing(6)

    def _next_safe_id(self, prefix: str) -> str:
        """Sinh ID không trùng với danh sách ID hiện có."""
        if prefix not in self._taken_ids:
            return prefix
        i = 2
        while f"{prefix}_{i}" in self._taken_ids:
            i += 1
        return f"{prefix}_{i}"

    def _apply_template(self, mode: str):
        """Điền trước các giá trị mẫu cho người dùng."""
        if mode == "vps":
            self.input_id.setText(self._next_safe_id("vps_cloud"))
            self.input_name.setText("Não AI VPS Đám mây (24/7)")
            self.input_url.setText("http://100.x.y.z:8080/v1")
            self.input_model.setText("google/gemini-2.5-flash")
            self.input_url.setFocus()
            self.input_url.selectAll()
        elif mode == "local":
            self.input_id.setText(self._next_safe_id("local_brain"))
            self.input_name.setText("Não AI Local (Máy tính)")
            self.input_url.setText("http://127.0.0.1:8000/v1")
            self.input_model.setText("qwen-2.5-coder")
            self.input_name.setFocus()

    def _clear_fields(self):
        """Xóa trắng các ô nhập liệu."""
        self.input_id.clear()
        self.input_name.clear()
        self.input_url.clear()
        self.input_key.clear()
        self.input_model.clear()
        self.lbl_test_status.clear()

    def _toggle_key_visibility(self):
        """Bật/tắt ẩn hiện API key."""
        if self.input_key.echoMode() == QLineEdit.EchoMode.Password:
            self.input_key.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_key.setText("🔒")
        else:
            self.input_key.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_key.setText("👁️")

    def _on_test_clicked(self):
        """Kiểm tra kết nối trực tiếp từ thông tin đang nhập trong form."""
        conn_id = self.input_id.text().strip() or "probe_conn"
        name = self.input_name.text().strip() or conn_id
        base_url = self.input_url.text().strip()
        api_key = self.input_key.text().strip()
        model = self.input_model.text().strip() or DEFAULT_MODEL_NAME

        if not base_url:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập Địa chỉ máy chủ (Base URL).")
            return
        try:
            temp_conn = HermesConnection.model_validate({
                "id": conn_id,
                "name": name,
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
            })
        except ValidationError as exc:
            QMessageBox.warning(self, "Kết nối không hợp lệ", validation_error_summary(exc))
            return

        self.btn_test.setEnabled(False)
        self.btn_test.setText("⏳ Đang kiểm tra...")
        self.lbl_test_status.setText("⏳ Đang kết nối tới máy chủ...")
        spawn_background_task(self._async_run_test(temp_conn), "dialog-test-connection")

    async def _async_run_test(self, temp_conn: HermesConnection):
        from src.bridge.hermes_client import HermesClient
        client = HermesClient(temp_conn)
        try:
            ok, message = await client.ping()
        except Exception as exc:
            ok, message = False, str(exc)
        finally:
            await client.close()
        if isValid(self):
            self.btn_test.setEnabled(True)
            self.btn_test.setText("🔌 Kiểm tra kết nối")
            status_icon = "✅" if ok else "❌"
            self.lbl_test_status.setText(f"{status_icon} {message}")
            if ok:
                QMessageBox.information(self, "Kết nối thành công", f"✅ {message}")
            else:
                QMessageBox.warning(self, "Kiểm tra thất bại", f"❌ {message}")

    def _on_accept(self):
        conn_id = self.input_id.text().strip()
        if not self.input_id.isReadOnly() and conn_id in self._taken_ids:
            QMessageBox.warning(self, "Trùng ID", f"ID '{conn_id}' đã tồn tại trong danh sách kết nối.")
            return
        if not conn_id:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập Mã định danh kết nối (ID).")
            return
        try:
            self.result_connection = HermesConnection.model_validate({
                "id": conn_id,
                "name": self.input_name.text().strip() or conn_id,
                "base_url": self.input_url.text().strip(),
                "api_key": self.input_key.text().strip(),
                "model": self.input_model.text().strip() or DEFAULT_MODEL_NAME,
            })
        except ValidationError as exc:
            QMessageBox.warning(self, "Kết nối không hợp lệ", validation_error_summary(exc))
            return
        self.accept()
