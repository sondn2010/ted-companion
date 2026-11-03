"""Mục Cài đặt "Đồng bộ dữ liệu": chế độ (PostgreSQL / Ted Sync API), máy chủ, tài khoản hoặc khoá API (keyring),
kiểm tra, đồng bộ ngay, xuất/nhập JSON."""

import asyncio
import json
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)
from pydantic import ValidationError
from shiboken6 import isValid

from src.config import settings
from src.core.background_task_spawner import spawn_background_task
from src.core.database_sync.database_sync_config import (
    DatabaseSyncConfig,
    DatabaseSyncImportError,
    build_export,
    parse_import,
)
from src.core.database_sync.database_sync_controller import database_sync_controller
from src.core.i18n import tr
from src.ui.button_text_escape import btn_text

logger = logging.getLogger("ted")

SSL_MODES = ("require", "verify-full", "verify-ca", "prefer", "allow", "disable")


def _load_saved_credentials() -> tuple[str, str]:
    from src.core.database_sync.postgres_connection_and_credentials import load_credentials

    try:
        return load_credentials()
    except Exception:  # không có backend keyring / dữ liệu hỏng → coi như chưa lưu
        logger.exception("Không đọc được tài khoản đồng bộ từ keyring")
        return "", ""


def _load_saved_api_key() -> str:
    from src.core.database_sync import api_sync_transport

    try:
        return api_sync_transport.load_api_key()
    except Exception:  # không có backend keyring → coi như chưa lưu
        logger.exception("Không đọc được khoá API đồng bộ từ keyring")
        return ""


class DatabaseSyncSettingsGroupWidget(QGroupBox):
    def __init__(self, parent=None):
        super().__init__(tr("db_sync_title"), parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.lbl_hint = QLabel(tr("db_sync_hint"))
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setObjectName("HintLabel")
        layout.addWidget(self.lbl_hint)

        form = QFormLayout()
        self._form = form
        self.combo_mode = QComboBox()
        self.combo_mode.addItem(tr("db_sync_mode_local"), "local_only")
        self.combo_mode.addItem(tr("db_sync_mode_postgres"), "postgres_sync")
        self.combo_mode.addItem(tr("db_sync_mode_api"), "api_sync")
        self.combo_mode.currentIndexChanged.connect(self._update_enabled)
        self.txt_host = QLineEdit()
        self.txt_host.setPlaceholderText("db.my-vps.com")
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535)
        self.txt_database = QLineEdit()
        self.txt_schema = QLineEdit()
        self.combo_ssl = QComboBox()
        self.combo_ssl.addItems(SSL_MODES)
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 240)
        self.txt_user = QLineEdit()
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_api_url = QLineEdit()
        self.txt_api_url.setPlaceholderText("https://ted.example.com")
        self.txt_api_key = QLineEdit()
        self.txt_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._rows = [
            ("db_sync_mode_label", self.combo_mode), ("db_sync_host", self.txt_host), ("db_sync_port", self.spin_port),
            ("db_sync_database", self.txt_database), ("db_sync_schema", self.txt_schema),
            ("db_sync_sslmode", self.combo_ssl), ("db_sync_interval", self.spin_interval),
            ("db_sync_user", self.txt_user), ("db_sync_password", self.txt_password),
            ("db_sync_api_url", self.txt_api_url), ("db_sync_api_key", self.txt_api_key),
        ]
        self._postgres_fields = (self.txt_host, self.spin_port, self.txt_database, self.txt_schema, self.combo_ssl,
                                 self.txt_user, self.txt_password)
        self._api_fields = (self.txt_api_url, self.txt_api_key)
        for key, field in self._rows:
            form.addRow(tr(key), field)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.btn_save = QPushButton(btn_text(tr("db_sync_btn_save")))
        self.btn_save.setObjectName("PrimaryBtn")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_test = QPushButton(btn_text(tr("db_sync_btn_test")))
        self.btn_test.clicked.connect(self._on_test)
        self.btn_sync_now = QPushButton(btn_text(tr("db_sync_btn_sync_now")))
        self.btn_sync_now.clicked.connect(database_sync_controller.sync_now)
        self.btn_import = QPushButton(f"📥 {tr('btn_import_json')}")
        self.btn_import.clicked.connect(self._on_import_json)
        self.btn_export = QPushButton(f"📤 {tr('btn_export_json')}")
        self.btn_export.clicked.connect(self._on_export_json)
        for btn in (self.btn_save, self.btn_test, self.btn_sync_now, self.btn_import, self.btn_export):
            buttons.addWidget(btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.lbl_status = QLabel(database_sync_controller.status_text)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.lbl_status)
        database_sync_controller.status_changed.connect(self._on_status_changed)

        self._fill_form(settings.database_sync)
        user, password = _load_saved_credentials()
        self.txt_user.setText(user)
        self._has_saved_password = bool(password)
        self._has_saved_api_key = bool(_load_saved_api_key())
        self._show_password_placeholder()

    # ---- form ⇄ config ----
    def _fill_form(self, config: DatabaseSyncConfig) -> None:
        self.combo_mode.setCurrentIndex(max(0, self.combo_mode.findData(config.mode)))
        self.txt_host.setText(config.host)
        self.spin_port.setValue(config.port)
        self.txt_database.setText(config.database)
        self.txt_schema.setText(config.schema_name)
        self.combo_ssl.setCurrentText(config.sslmode)
        self.spin_interval.setValue(config.sync_interval_minutes)
        self.txt_api_url.setText(config.api_url)
        self._update_enabled()

    def _form_config(self) -> DatabaseSyncConfig:
        return DatabaseSyncConfig(
            mode=self.combo_mode.currentData(), host=self.txt_host.text().strip(), port=self.spin_port.value(),
            database=self.txt_database.text().strip(), schema=self.txt_schema.text().strip(),
            sslmode=self.combo_ssl.currentText(), sync_interval_minutes=self.spin_interval.value(),
            api_url=self.txt_api_url.text(),
        )

    def _form_credentials(self) -> tuple[str, str]:
        """Ô mật khẩu trống + đã lưu trước đó → dùng mật khẩu đã lưu."""
        password = self.txt_password.text()
        if not password and self._has_saved_password:
            password = _load_saved_credentials()[1]
        return self.txt_user.text().strip(), password

    def _update_enabled(self) -> None:
        mode = self.combo_mode.currentData()
        on = mode != "local_only"
        for _key, field in self._rows[1:]:
            field.setEnabled(on)
        # Chế độ API chỉ cần URL + khoá; các chế độ khác hiện ô PostgreSQL như cũ
        for field in self._postgres_fields:
            self._form.setRowVisible(field, mode != "api_sync")
        for field in self._api_fields:
            self._form.setRowVisible(field, mode == "api_sync")
        self.btn_test.setEnabled(on)
        self.btn_sync_now.setEnabled(on)

    def _show_password_placeholder(self) -> None:
        self.txt_password.clear()
        self.txt_password.setPlaceholderText(tr("db_sync_password_saved") if self._has_saved_password else "")
        self.txt_api_key.clear()
        self.txt_api_key.setPlaceholderText(tr("db_sync_api_key_saved") if self._has_saved_api_key else "")

    def _validated_config(self) -> DatabaseSyncConfig | None:
        try:
            config = self._form_config()
        except ValidationError as exc:
            QMessageBox.warning(self, self.title(), tr("db_sync_import_invalid",
                                                       error="; ".join(e["msg"] for e in exc.errors())))
            return None
        if config.mode == "postgres_sync" and not (config.host and self.txt_user.text().strip()):
            QMessageBox.warning(self, self.title(), tr("db_sync_host_required"))
            return None
        if config.mode == "api_sync" and not (config.api_url and self._form_api_key()):
            QMessageBox.warning(self, self.title(), tr("db_sync_api_url_required"))
            return None
        return config

    def _form_api_key(self) -> str:
        """Ô khoá trống + đã lưu trước đó → dùng khoá đã lưu."""
        return self.txt_api_key.text().strip() or (_load_saved_api_key() if self._has_saved_api_key else "")

    # ---- actions ----
    def _on_save(self) -> None:
        config = self._validated_config()
        if config is None:
            return
        if config.mode == "postgres_sync":
            from src.core.database_sync.postgres_connection_and_credentials import save_credentials

            try:
                save_credentials(*self._form_credentials())
            except Exception as exc:
                QMessageBox.warning(self, self.title(), tr("db_sync_keyring_error", error=str(exc)))
                return
            self._has_saved_password = self._has_saved_password or bool(self.txt_password.text())
            self._show_password_placeholder()
        if config.mode == "api_sync" and self.txt_api_key.text().strip():
            from src.core.database_sync import api_sync_transport

            try:
                api_sync_transport.save_api_key(self.txt_api_key.text().strip())
            except Exception as exc:
                QMessageBox.warning(self, self.title(), tr("db_sync_keyring_error", error=str(exc)))
                return
            self._has_saved_api_key = True
            self._show_password_placeholder()
        settings.database_sync = config
        settings.save()
        database_sync_controller.reconfigure()
        QMessageBox.information(self, self.title(), tr("db_sync_saved"))

    def _on_test(self) -> None:
        config = self._validated_config()
        if config is None:
            return
        self.btn_test.setEnabled(False)
        self.btn_test.setText(btn_text(tr("db_sync_testing")))
        if config.mode == "api_sync":
            spawn_background_task(self._run_api_test(config.api_url, self._form_api_key()), name="database_sync_test")
            return
        spawn_background_task(self._run_test(config, *self._form_credentials()), name="database_sync_test")

    async def _run_test(self, config: DatabaseSyncConfig, user: str, password: str) -> None:
        from src.core.database_sync.postgres_connection_and_credentials import connect_postgres
        from src.core.database_sync.postgres_sync_row_store import ensure_schema

        def check():
            with connect_postgres(config, user, password) as conn:
                ensure_schema(conn, config.schema_name)  # kiểm tra luôn quyền tạo schema/bảng

        try:
            await asyncio.to_thread(check)
            ok, message = True, tr("db_sync_test_ok")
        except Exception as exc:
            ok, message = False, tr("db_sync_test_failed", error=str(exc))
        if not isValid(self):
            return
        self.btn_test.setEnabled(True)
        self.btn_test.setText(btn_text(tr("db_sync_btn_test")))
        (QMessageBox.information if ok else QMessageBox.warning)(self, self.title(), message)

    async def _run_api_test(self, api_url: str, api_key: str) -> None:
        from src.core.database_sync import api_sync_transport
        from src.core.database_sync.database_sync_controller import fill_user_name_from_server

        try:
            me = await asyncio.to_thread(api_sync_transport.fetch_me, api_url, api_key)
            ok, message = True, tr("db_sync_api_test_ok", name=me.get("name", ""))
            fill_user_name_from_server(me.get("name"))
        except api_sync_transport.ApiKeyRejected:
            ok, message = False, tr("db_sync_api_key_rejected")
        except Exception as exc:
            ok, message = False, tr("db_sync_api_test_failed", error=str(exc))
        if not isValid(self):
            return
        self.btn_test.setEnabled(True)
        self.btn_test.setText(btn_text(tr("db_sync_btn_test")))
        (QMessageBox.information if ok else QMessageBox.warning)(self, self.title(), message)

    def _on_export_json(self) -> None:
        config = self._validated_config()
        if config is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("db_sync_export_title"), "ted_database_sync.json",
                                              "JSON Files (*.json);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(build_export(config), fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            QMessageBox.warning(self, self.title(), tr("db_sync_file_error", error=str(exc)))
            return
        QMessageBox.information(self, self.title(), tr("db_sync_export_done", path=path))

    def _on_import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("db_sync_import_title"), "", "JSON Files (*.json);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, self.title(), tr("db_sync_file_error", error=str(exc)))
            return
        try:
            config = parse_import(raw, settings.database_sync)
        except DatabaseSyncImportError as exc:
            QMessageBox.warning(self, self.title(), tr(f"db_sync_import_{exc.code}", version=exc.detail, error=exc.detail))
            return
        self._fill_form(config)  # chỉ nạp vào form; người dùng nhập tài khoản rồi tự Lưu
        self.txt_user.clear()
        self._has_saved_password = False
        self._has_saved_api_key = False
        self._show_password_placeholder()
        self.txt_user.setFocus()
        QMessageBox.information(self, self.title(), tr("db_sync_import_done"))

    def _on_status_changed(self, text: str) -> None:
        if isValid(self):
            self.lbl_status.setText(text)

    def retranslate_ui(self) -> None:
        self.setTitle(tr("db_sync_title"))
        self.lbl_hint.setText(tr("db_sync_hint"))
        for row, (key, _field) in enumerate(self._rows):
            self._form.itemAt(row, QFormLayout.ItemRole.LabelRole).widget().setText(tr(key))
        self.combo_mode.setItemText(0, tr("db_sync_mode_local"))
        self.combo_mode.setItemText(1, tr("db_sync_mode_postgres"))
        self.combo_mode.setItemText(2, tr("db_sync_mode_api"))
        self.btn_save.setText(btn_text(tr("db_sync_btn_save")))
        self.btn_test.setText(btn_text(tr("db_sync_btn_test")))
        self.btn_sync_now.setText(btn_text(tr("db_sync_btn_sync_now")))
        self.btn_import.setText(f"📥 {tr('btn_import_json')}")
        self.btn_export.setText(f"📤 {tr('btn_export_json')}")
        self._show_password_placeholder()
