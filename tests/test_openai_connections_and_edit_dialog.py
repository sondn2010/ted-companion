"""Unit tests cho HermesConnectionsSettingsWidget và HermesConnectionEditDialog."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QLineEdit

from src.core.connection_registry_and_settings_migration import HermesConnection
from src.ui.dashboard_tabs.hermes_connection_edit_dialog import HermesConnectionEditDialog
from src.ui.dashboard_tabs.hermes_connections_settings_widget import HermesConnectionsSettingsWidget
from tests.qt_offscreen_app_helper import get_qapp


@pytest.fixture(autouse=True)
def qapp():
    return get_qapp()


def test_hermes_connection_edit_dialog_prefills_vps_template_by_default():
    dialog = HermesConnectionEditDialog(taken_ids=frozenset(["vps_cloud"]))
    assert dialog._is_editing is False

    # Do "vps_cloud" đã bị chiếm nên sinh ID an toàn kế tiếp
    assert dialog.input_id.text() == "vps_cloud_2"
    assert "Não AI VPS" in dialog.input_name.text()
    assert "8080/v1" in dialog.input_url.text()
    assert "gemini" in dialog.input_model.text()

    # Panel trợ giúp hiển thị thông tin tác giả và giải thích
    help_text = dialog.help_browser.toHtml()
    assert "Son Do" in help_text
    assert "sondn2010@gmail.com" in help_text
    assert "Base URL" in help_text


def test_hermes_connection_edit_dialog_apply_local_template():
    dialog = HermesConnectionEditDialog(taken_ids=frozenset())
    dialog._apply_template("local")

    assert dialog.input_id.text() == "local_brain"
    assert "Local" in dialog.input_name.text()
    assert dialog.input_url.text() == "http://127.0.0.1:8000/v1"
    assert dialog.input_model.text() == "qwen-2.5-coder"


def test_hermes_connection_edit_dialog_toggle_key_visibility():
    dialog = HermesConnectionEditDialog()
    assert dialog.input_key.echoMode() == QLineEdit.EchoMode.Password

    # Toggle sang hiển thị
    dialog.btn_toggle_key.click()
    assert dialog.input_key.echoMode() == QLineEdit.EchoMode.Normal
    assert dialog.btn_toggle_key.text() == "🔒"

    # Toggle lại ẩn
    dialog.btn_toggle_key.click()
    assert dialog.input_key.echoMode() == QLineEdit.EchoMode.Password
    assert dialog.btn_toggle_key.text() == "👁️"


def test_hermes_connection_edit_dialog_existing_connection():
    existing = HermesConnection(
        id="work_custom",
        name="Kết nối công ty",
        base_url="https://api.mycompany.com/v1",
        api_key="sk-secret-123",
        model="gpt-4o",
    )
    dialog = HermesConnectionEditDialog(existing=existing)
    assert dialog._is_editing is True
    assert dialog.input_id.text() == "work_custom"
    assert dialog.input_id.isReadOnly() is True
    assert dialog.input_name.text() == "Kết nối công ty"
    assert dialog.input_url.text() == "https://api.mycompany.com/v1"
    assert dialog.input_key.text() == "sk-secret-123"
    assert dialog.input_model.text() == "gpt-4o"


def test_hermes_connections_settings_widget_layout_and_buttons():
    config = SimpleNamespace(
        connections=[
            HermesConnection(id="c1", name="C1", base_url="http://localhost:8000/v1", model="m1"),
        ],
        save=MagicMock(),
        get_connection=lambda cid: HermesConnection(id="c1", name="C1", base_url="http://localhost:8000/v1", model="m1"),
    )
    pool = SimpleNamespace(get=MagicMock(), drop=MagicMock())
    registry = SimpleNamespace(enabled=lambda: [], connection_for=lambda mid: None)

    widget = HermesConnectionsSettingsWidget(config, pool, registry)
    # Các nút trên thanh công cụ
    assert widget.btn_add.text().startswith("➕")
    assert widget.btn_test_all.text().startswith("⚡")
    assert widget.btn_import.text().startswith("📥")
    assert widget.btn_export.text().startswith("📤")
    assert widget.btn_delete.text().startswith("🗑️")
    assert widget.btn_clone.text().startswith("📋")
    assert widget.btn_edit.text().startswith("✏️")
    assert widget.btn_test.text().startswith("🔌")

    # Menu chuột phải được kích hoạt trên bảng
    from PySide6.QtCore import Qt
    assert widget.table.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu

    # Bảng có dòng dữ liệu
    assert widget.table.rowCount() == 1
    assert widget.table.item(0, 0).text() == "C1"
    assert hasattr(widget, "txt_search")


def test_hermes_connections_search_filter():
    conns = [
        HermesConnection(id="vps_work", name="Não AI Công việc", base_url="http://vps:8080/v1", model="gemini-2.5-flash"),
        HermesConnection(id="local_tutor", name="Não AI Gia sư", base_url="http://127.0.0.1:8000/v1", model="hermes-agent"),
        HermesConnection(id="deepseek_math", name="Toán Cấp 2", base_url="http://math:8000/v1", model="deepseek-r1"),
    ]
    config = SimpleNamespace(
        connections=conns,
        get_connection=lambda cid: next((c for c in conns if c.id == cid), None),
        save=MagicMock(),
    )
    pool = SimpleNamespace(get=MagicMock(), drop=MagicMock())
    registry = SimpleNamespace(enabled=lambda: [], connection_for=lambda mid: None)

    widget = HermesConnectionsSettingsWidget(config, pool, registry)
    assert hasattr(widget, "txt_search")
    assert widget.table.rowCount() == 3

    # 1. Lọc theo tên
    widget.txt_search.setText("Gia sư")
    assert widget.table.isRowHidden(0) is True
    assert widget.table.isRowHidden(1) is False
    assert widget.table.isRowHidden(2) is True

    # 2. Lọc theo model
    widget.txt_search.setText("deepseek")
    assert widget.table.isRowHidden(0) is True
    assert widget.table.isRowHidden(1) is True
    assert widget.table.isRowHidden(2) is False

    # 3. Xóa tìm kiếm -> hiển thị lại tất cả
    widget.txt_search.setText("")
    assert widget.table.isRowHidden(0) is False
    assert widget.table.isRowHidden(1) is False
    assert widget.table.isRowHidden(2) is False


def test_hermes_connection_edit_dialog_test_button_and_clone_mode(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    # 1. Nút kiểm tra kết nối có mặt cả khi thêm mới
    new_dlg = HermesConnectionEditDialog()
    assert hasattr(new_dlg, "btn_test")
    assert "Kiểm tra" in new_dlg.btn_test.text()

    # 2. Chế độ nhân bản (is_clone=True)
    existing = HermesConnection(
        id="c1",
        name="C1",
        base_url="http://localhost:8000/v1",
        model="m1",
    )
    clone_dlg = HermesConnectionEditDialog(existing=existing, is_clone=True)
    assert clone_dlg._is_clone is True
    assert clone_dlg._is_editing is False
    assert clone_dlg.input_id.isReadOnly() is False
    assert "Nhân bản" in clone_dlg.windowTitle()
    assert hasattr(clone_dlg, "btn_test")


def test_brain_select_dialog_search_filter_and_selection():
    from src.ui.dashboard_tabs.brain_select_dialog import BrainSelectDialog

    conns = [
        HermesConnection(id="vps_work", name="Não AI Công việc", base_url="http://vps.cloud:8080/v1", model="gemini-2.5-flash"),
        HermesConnection(id="local_tutor", name="Não AI Gia sư", base_url="http://127.0.0.1:8000/v1", model="hermes-agent"),
        HermesConnection(id="math_brain", name="Toán Cấp 2", base_url="http://math.server:8000/v1", model="qwen-coder"),
    ]

    dialog = BrainSelectDialog(connections=conns, current_id="local_tutor", module_name="Gia sư", can_clear=True)
    assert dialog.table.rowCount() == 3

    # Dòng đang chọn có badge ⭐
    assert "⭐" in dialog.table.item(1, 3).text()

    # Tìm kiếm theo tên hoặc model
    dialog.txt_search.setText("toán")
    assert dialog.table.isRowHidden(0) is True
    assert dialog.table.isRowHidden(1) is True
    assert dialog.table.isRowHidden(2) is False

    # Tìm kiếm theo model
    dialog.txt_search.setText("flash")
    assert dialog.table.isRowHidden(0) is False
    assert dialog.table.isRowHidden(1) is True
    assert dialog.table.isRowHidden(2) is True

    # Xóa tìm kiếm -> hiển thị lại tất cả
    dialog.txt_search.setText("")
    assert dialog.table.isRowHidden(0) is False
    assert dialog.table.isRowHidden(1) is False
    assert dialog.table.isRowHidden(2) is False

    # Chọn một dòng
    dialog.table.selectRow(0)
    dialog._on_select_clicked()
    assert dialog.selected_connection_id == "vps_work"

    # Thử nút Bỏ chọn (clear)
    dialog._on_clear_clicked()
    assert dialog.selected_connection_id is None


def test_modules_toggle_settings_widget_brain_pick_button_and_dialog(monkeypatch):
    from PySide6.QtWidgets import QPushButton
    from src.modules_runtime.module_manifest_schema import ModuleManifest
    from src.ui.dashboard_tabs.modules_toggle_settings_widget import ModulesToggleSettingsWidget

    manifests = [
        ModuleManifest(
            id="coach",
            name="Học tập",
            engine="coach",
            connection="vps_work",
            learner_id="uyen",
            icon="🎓",
        )
    ]
    conns = [
        HermesConnection(id="vps_work", name="Não AI VPS", base_url="http://vps:8080/v1", model="gemini"),
    ]
    config = SimpleNamespace(
        connections=conns,
        get_connection=lambda cid: next((c for c in conns if c.id == cid), None),
        save=MagicMock(),
        set_module_override=MagicMock(),
    )
    registry = SimpleNamespace(
        all=lambda: manifests,
        is_enabled=lambda mid: True,
        connection_for=lambda mid: "vps_work",
        active=lambda: None,
        errors={},
        modules_changed=MagicMock(connect=MagicMock(), emit=MagicMock()),
    )

    widget = ModulesToggleSettingsWidget(config, registry)

    # 1. Có nút Quản lý kết nối tới Não AI trên tiêu đề
    assert hasattr(widget, "btn_manage_connections")
    assert "Quản lý Kết nối tới Não AI" in widget.btn_manage_connections.text()

    # 2. Module có nút chọn Não AI dạng QPushButton (thay vì dropdown)
    assert "coach" in widget._brain_buttons
    pick_btn = widget._brain_buttons["coach"]
    assert isinstance(pick_btn, QPushButton)
    assert "Não AI VPS" in pick_btn.text()


def test_hermes_connections_manage_dialog():
    from src.ui.dashboard_tabs.hermes_connections_manage_dialog import HermesConnectionsManageDialog

    conns = [
        HermesConnection(id="c1", name="C1", base_url="http://localhost:8000/v1", model="m1"),
    ]
    config = SimpleNamespace(
        connections=conns,
        get_connection=lambda cid: next((c for c in conns if c.id == cid), None),
        save=MagicMock(),
    )
    pool = SimpleNamespace(get=MagicMock(), drop=MagicMock())
    registry = SimpleNamespace(enabled=lambda: [], connection_for=lambda mid: None)

    dialog = HermesConnectionsManageDialog(config, pool, registry)
    assert hasattr(dialog, "connections_widget")
    assert hasattr(dialog, "btn_close")
    assert "Não AI" in dialog.windowTitle()


def test_hermes_connections_settings_widget_clone_action(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    conns = [
        HermesConnection(id="work", name="Work Brain", base_url="http://localhost:8080/v1", model="gemini"),
    ]
    upserted = []
    config = SimpleNamespace(
        connections=conns,
        get_connection=lambda cid: next((c for c in conns if c.id == cid), None),
        upsert_connection=lambda c: (upserted.append(c), conns.append(c)),
        save=MagicMock(),
    )
    pool = SimpleNamespace(get=MagicMock(), drop=MagicMock())
    registry = SimpleNamespace(enabled=lambda: [], connection_for=lambda mid: None)

    widget = HermesConnectionsSettingsWidget(config, pool, registry)
    widget.table.selectRow(0)

    # Giả lập người dùng bấm Clone và Save trong dialog
    monkeypatch.setattr(
        HermesConnectionEditDialog,
        "exec",
        lambda self: setattr(self, "result_connection", HermesConnection(
            id="work_copy",
            name="Work Brain (Bản sao)",
            base_url="http://localhost:8080/v1",
            model="gemini",
        )) or 1,
    )

    widget._on_clone()
    assert len(upserted) == 1
    assert upserted[0].id == "work_copy"
    assert "Bản sao" in upserted[0].name


@pytest.mark.asyncio
async def test_hermes_connections_settings_widget_test_all_async(monkeypatch):
    conns = [
        HermesConnection(id="c1", name="C1", base_url="http://localhost:8000/v1", model="m1"),
        HermesConnection(id="c2", name="C2", base_url="http://localhost:8001/v1", model="m2"),
    ]
    config = SimpleNamespace(
        connections=conns,
        get_connection=lambda cid: next((c for c in conns if c.id == cid), None),
        save=MagicMock(),
    )
    mock_client = SimpleNamespace(
        ping=MagicMock(return_value=(True, "OK")),
    )
    # async ping
    async def async_ping():
        return True, "Kết nối tốt"
    mock_client.ping = async_ping

    pool = SimpleNamespace(get=lambda cid: mock_client, drop=MagicMock())
    registry = SimpleNamespace(enabled=lambda: [], connection_for=lambda mid: None)

    widget = HermesConnectionsSettingsWidget(config, pool, registry)
    await widget._run_test_all()

    assert "✅" in widget.table.item(0, 3).text()
    assert "✅" in widget.table.item(1, 3).text()


def test_hermes_connections_delete_requires_confirmation(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    conns = [
        HermesConnection(id="c1", name="C1", base_url="http://localhost:8000/v1", model="m1"),
        HermesConnection(id="c2", name="C2", base_url="http://localhost:8001/v1", model="m2"),
    ]
    deleted_ids = []
    config = SimpleNamespace(
        connections=conns,
        get_connection=lambda cid: next((c for c in conns if c.id == cid), None),
        delete_connection=lambda cid: (deleted_ids.append(cid), conns.pop(0), None)[2],
        save=MagicMock(),
    )
    pool = SimpleNamespace(get=MagicMock(), drop=MagicMock())
    registry = SimpleNamespace(enabled=lambda: [], connection_for=lambda mid: None)

    widget = HermesConnectionsSettingsWidget(config, pool, registry)
    widget.table.selectRow(0)

    # 1. Người dùng bấm No trong hộp thoại xác nhận -> Không xóa
    question_called = []

    def mock_question_no(*args, **kwargs):
        question_called.append(True)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", mock_question_no)
    widget._on_delete()
    assert len(question_called) == 1
    assert len(deleted_ids) == 0

    # 2. Người dùng bấm Yes trong hộp thoại xác nhận -> Tiến hành xóa
    def mock_question_yes(*args, **kwargs):
        question_called.append(True)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", mock_question_yes)
    widget._on_delete()
    assert len(question_called) == 2
    assert len(deleted_ids) == 1
    assert deleted_ids[0] == "c1"


def test_hermes_connections_export_and_import_json(tmp_path, monkeypatch):
    import json
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    conns = [
        HermesConnection(id="c1", name="C1", base_url="http://localhost:8000/v1", model="m1"),
        HermesConnection(id="c2", name="C2", base_url="http://localhost:8001/v1", model="m2"),
    ]
    config = SimpleNamespace(
        connections=list(conns),
        get_connection=lambda cid: next((c for c in config.connections if c.id == cid), None),
        upsert_connection=lambda c: config.connections.append(c),
        save=MagicMock(),
    )
    pool = SimpleNamespace(get=MagicMock(), drop=MagicMock())
    registry = SimpleNamespace(enabled=lambda: [], connection_for=lambda mid: None)

    widget = HermesConnectionsSettingsWidget(config, pool, registry)

    # Test Export
    export_file = tmp_path / "exported_brains.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(export_file), "json"))
    widget._on_export_json()

    assert export_file.exists()
    content = json.loads(export_file.read_text(encoding="utf-8"))
    assert "connections" in content
    assert len(content["connections"]) == 2
    assert content["connections"][0]["id"] == "c1"

    # Test Import
    import_file = tmp_path / "import_brains.json"
    import_data = {
        "connections": [
            {"id": "new_c3", "name": "C3 Mới", "base_url": "http://localhost:8002/v1", "model": "m3"}
        ]
    }
    import_file.write_text(json.dumps(import_data), encoding="utf-8")

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(import_file), "json"))
    widget._on_import_json()

    assert any(c.id == "new_c3" for c in config.connections)



