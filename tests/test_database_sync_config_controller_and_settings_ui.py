"""Cấu hình đồng bộ dữ liệu: lưu settings, xuất/nhập JSON (không bao giờ có tài khoản/mật khẩu), controller, mục Cài đặt."""

import json
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from tests.qt_offscreen_app_helper import get_qapp

from src.config import AppConfig, settings
from src.core.database_sync import postgres_connection_and_credentials as creds
from src.core.database_sync.database_sync_config import (
    DatabaseSyncConfig,
    DatabaseSyncImportError,
    build_export,
    parse_import,
)
from src.core.database_sync.database_sync_controller import DatabaseSyncController
from src.core.i18n import TRANSLATIONS

VPS = DatabaseSyncConfig(mode="postgres_sync", host="db.vps.example", port=6543, database="ted_prod",
                         schema="ted_sync", sslmode="verify-full", sync_interval_minutes=45)


# ---- cấu hình + xuất/nhập ----

def test_settings_round_trip_keeps_database_sync(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    assert config.database_sync.mode == "local_only"
    config.database_sync = VPS
    config.save()
    assert AppConfig(data_dir=tmp_path).database_sync == VPS


def test_invalid_database_sync_in_settings_falls_back_to_local_only(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"database_sync": {"port": 0}}), encoding="utf-8")
    assert AppConfig(data_dir=tmp_path).database_sync == DatabaseSyncConfig()


def test_export_has_every_setting_but_no_credentials():
    exported = build_export(VPS)
    assert (exported["app"], exported["kind"], exported["version"]) == ("Ted Companion", "database_sync", 1)
    assert exported["database"] == {"mode": "postgres_sync", "host": "db.vps.example", "port": 6543,
                                    "database": "ted_prod", "schema": "ted_sync", "sslmode": "verify-full",
                                    "sync_interval_minutes": 45, "api_url": ""}
    text = json.dumps(exported).lower()
    assert "user" not in text and "password" not in text


def test_import_round_trip_and_ignores_credentials_and_unknown_keys():
    exported = build_export(VPS)
    exported["database"].update(user="hacker", password="secret", future_option=True)
    assert parse_import(exported, DatabaseSyncConfig()) == VPS


def test_import_missing_keys_keep_current_values():
    raw = {"app": "Ted Companion", "kind": "database_sync", "version": 1, "database": {"host": "new.host"}}
    assert parse_import(raw, VPS) == VPS.model_copy(update={"host": "new.host"})


@pytest.mark.parametrize("raw, code", [
    ({"app": "Ted Companion", "version": 1, "connections": []}, "wrong_file"),          # file Não AI
    ([1, 2], "wrong_file"),
    ({"app": "Ted Companion", "kind": "database_sync", "version": 2, "database": {}}, "unsupported_version"),
    ({"app": "Ted Companion", "kind": "database_sync", "version": 1, "database": {"port": 99999}}, "invalid"),
    ({"app": "Ted Companion", "kind": "database_sync", "version": 1, "database": {"schema": "Drop;"}}, "invalid"),
])
def test_import_rejects_bad_files(raw, code):
    with pytest.raises(DatabaseSyncImportError) as err:
        parse_import(raw, DatabaseSyncConfig())
    assert err.value.code == code


def test_strings_have_vi_en_parity():
    from src.core.i18n_database_sync_strings import DATABASE_SYNC_EN, DATABASE_SYNC_VI

    assert DATABASE_SYNC_VI.keys() == DATABASE_SYNC_EN.keys()
    assert "db_sync_title" in TRANSLATIONS["en"]


# ---- controller ----

def test_controller_stays_off_in_local_only_mode(monkeypatch, memory_engine):
    get_qapp()
    monkeypatch.setattr(settings, "database_sync", DatabaseSyncConfig())
    controller = DatabaseSyncController()
    controller.start(memory_engine)
    assert controller._service is None
    assert controller.status_text == TRANSLATIONS[settings.language]["db_sync_status_off"]
    controller.flush_on_exit()  # không có service → không làm gì


def test_flush_on_exit_runs_one_last_sync_and_survives_errors():
    get_qapp()
    controller = DatabaseSyncController()
    calls = []
    controller._service = SimpleNamespace(sync_once=lambda: calls.append(1) or 1 / 0)
    controller.flush_on_exit(timeout=5)
    assert calls == [1]


# ---- mục Cài đặt ----

@pytest.fixture
def widget(monkeypatch, api_keyring):   # api_keyring: không bao giờ chạm keyring thật
    get_qapp()
    saved = {}
    monkeypatch.setattr(creds, "load_credentials", lambda: (saved.get("user", ""), saved.get("password", "")))
    monkeypatch.setattr(creds, "save_credentials", lambda u, p: saved.update(user=u, password=p))
    monkeypatch.setattr(settings, "database_sync", DatabaseSyncConfig())
    monkeypatch.setattr(settings, "save", lambda: None)
    for name in ("information", "warning"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: None)
    from src.ui.dashboard_tabs import database_sync_settings_group_widget as mod

    monkeypatch.setattr(mod.database_sync_controller, "reconfigure", lambda: None)
    w = mod.DatabaseSyncSettingsGroupWidget()
    w.saved_credentials = saved
    yield w
    w.deleteLater()


def test_save_stores_config_in_settings_and_credentials_in_keyring(widget):
    widget._fill_form(VPS)
    widget.txt_user.setText("ted_sync")
    widget.txt_password.setText("s3cret")
    widget._on_save()
    assert settings.database_sync == VPS
    assert widget.saved_credentials == {"user": "ted_sync", "password": "s3cret"}
    assert widget.txt_password.text() == ""  # không giữ mật khẩu trong ô sau khi lưu

    widget._on_save()  # để trống mật khẩu = giữ mật khẩu đã lưu
    assert widget.saved_credentials["password"] == "s3cret"


def test_export_then_import_on_new_machine_needs_credentials_again(widget, tmp_path, monkeypatch):
    path = tmp_path / "ted_database_sync.json"
    widget._fill_form(VPS)
    widget.txt_user.setText("ted_sync")
    widget.txt_password.setText("s3cret")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
    widget._on_export_json()
    content = path.read_text(encoding="utf-8")
    assert "ted_sync\"" in content and "s3cret" not in content and "user" not in content

    widget._fill_form(DatabaseSyncConfig())
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    widget._on_import_json()
    assert widget._form_config() == VPS
    assert widget.txt_user.text() == "" and widget.txt_password.text() == ""
    assert settings.database_sync == DatabaseSyncConfig()  # nhập chỉ nạp form, chưa lưu


def test_save_requires_host_and_username(widget):
    widget._fill_form(VPS)
    widget.txt_user.setText("")
    widget._on_save()
    assert settings.database_sync == DatabaseSyncConfig()


def test_local_change_schedules_a_debounced_sync_once(memory_engine):
    from src.core.database_sync.sqlite_change_capture_triggers import install_sync_triggers

    get_qapp()
    install_sync_triggers(memory_engine)
    controller = DatabaseSyncController()
    controller._engine = memory_engine
    controller._check_local_changes()
    assert not controller._debounce.isActive()  # outbox rỗng

    with memory_engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO sync_outbox VALUES ('task', '[\"t1\"]', '2026-10-29T10:00:00.000Z')")
    controller._check_local_changes()
    assert controller._debounce.isActive()

    controller._debounce.stop()
    controller._check_local_changes()  # cùng mốc → không hẹn lại
    assert not controller._debounce.isActive()


# ---- chế độ API sync ----

API = DatabaseSyncConfig(mode="api_sync", api_url="https://ted.example.com", sync_interval_minutes=30)


@pytest.fixture
def api_keyring(monkeypatch):
    from src.core.database_sync import api_sync_transport

    stored = {}
    monkeypatch.setattr(api_sync_transport, "load_api_key", lambda: stored.get("key", ""))
    monkeypatch.setattr(api_sync_transport, "save_api_key", lambda key: stored.update(key=key))
    return stored


def test_api_mode_shows_api_fields_only(api_keyring, widget):
    widget._fill_form(API)
    assert widget._form.isRowVisible(widget.txt_api_url) and widget._form.isRowVisible(widget.txt_api_key)
    assert not widget._form.isRowVisible(widget.txt_host) and not widget._form.isRowVisible(widget.txt_password)
    assert widget.txt_api_url.text() == "https://ted.example.com"
    widget._fill_form(VPS)
    assert widget._form.isRowVisible(widget.txt_host) and not widget._form.isRowVisible(widget.txt_api_url)


def test_save_api_mode_stores_key_in_keyring_not_settings(api_keyring, widget):
    widget._fill_form(API)
    widget.txt_api_key.setText("ted_secret_key")
    widget._on_save()
    assert settings.database_sync == API
    assert api_keyring == {"key": "ted_secret_key"}
    assert widget.txt_api_key.text() == ""   # không giữ khoá trong ô sau khi lưu
    assert "ted_secret_key" not in json.dumps(settings.database_sync.to_payload())
    widget._on_save()   # để trống = giữ khoá đã lưu
    assert api_keyring == {"key": "ted_secret_key"}


def test_api_mode_requires_url_and_key(api_keyring, widget):
    widget._fill_form(DatabaseSyncConfig(mode="api_sync"))
    widget.txt_api_key.setText("ted_k")
    widget._on_save()
    assert settings.database_sync == DatabaseSyncConfig()
    widget._fill_form(API)   # có URL nhưng chưa có khoá nào
    widget.txt_api_key.clear()
    widget._on_save()
    assert settings.database_sync == DatabaseSyncConfig()


def test_api_test_connection_shows_name_and_fills_empty_user_name(api_keyring, widget, monkeypatch):
    import asyncio

    from src.core.database_sync import api_sync_transport

    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, text: shown.append(text))
    monkeypatch.setattr(api_sync_transport, "fetch_me", lambda url, key: {"user_id": "u1", "name": f"An@{url}/{key}"})
    monkeypatch.setattr(settings, "user_name", "")
    asyncio.run(widget._run_api_test("https://ted.example.com", "ted_k"))
    assert shown == [TRANSLATIONS[settings.language]["db_sync_api_test_ok"].format(name="An@https://ted.example.com/ted_k")]
    assert settings.user_name == "An@https://ted.example.com/ted_k"[:40]
