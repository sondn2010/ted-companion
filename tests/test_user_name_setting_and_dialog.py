"""Tên người dùng: lưu trong settings.json, hỏi 1 lần lúc mở app (có "Để sau"), thay cho tên cứng "Uyên"."""

import pytest

from tests.qt_offscreen_app_helper import get_qapp


@pytest.fixture
def fresh_settings(tmp_path):
    from src.config import AppConfig

    return AppConfig(data_dir=tmp_path)


def test_user_name_persists_roundtrip(tmp_path, fresh_settings):
    from src.config import AppConfig

    fresh_settings.set_user_name("  Minh  ")
    fresh_settings.save()
    assert AppConfig(data_dir=tmp_path).user_name == "Minh"


def test_user_name_trim_and_limit(fresh_settings):
    fresh_settings.set_user_name("   ")
    assert fresh_settings.user_name == ""
    fresh_settings.set_user_name("x" * 50)
    assert fresh_settings.user_name == "x" * 40


def test_display_name_fallback(fresh_settings):
    from src.core.i18n import tr

    assert fresh_settings.user_display_name == tr("user_name_fallback")
    fresh_settings.set_user_name("Minh")
    assert fresh_settings.user_display_name == "Minh"


@pytest.fixture
def app_settings(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "user_name", "")
    monkeypatch.setattr(settings, "save", lambda: None)
    return settings


def test_dialog_saves_name(app_settings):
    from src.ui.user_name_dialog import UserNameDialog

    get_qapp()
    dialog = UserNameDialog()
    assert not dialog.btn_ok.isEnabled()
    dialog.txt_name.setText("  Minh ")
    assert dialog.btn_ok.isEnabled()
    dialog.accept()
    assert app_settings.user_name == "Minh"


def test_dialog_later_keeps_empty(app_settings):
    from src.ui.user_name_dialog import UserNameDialog

    get_qapp()
    dialog = UserNameDialog()
    dialog.txt_name.setText("Minh")
    dialog.reject()
    assert app_settings.user_name == ""


def test_dialog_skipped_when_name_set(app_settings, monkeypatch):
    import src.ui.user_name_dialog as mod

    def boom(*_a, **_k):
        raise AssertionError("dialog must not be built")

    monkeypatch.setattr(mod, "UserNameDialog", boom)
    app_settings.user_name = "Minh"
    mod.ask_user_name_if_missing()


def test_no_hard_coded_uyen_in_activity_wiring():
    from pathlib import Path

    import src.ui.activity_monitor_wiring as wiring
    import src.core.activity_watcher.activity_outbox_sender as sender

    for module in (wiring, sender):
        assert "Uyên" not in Path(module.__file__).read_text(encoding="utf-8")


def test_settings_tab_edits_user_name(app_settings, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from PySide6.QtWidgets import QMessageBox

    from src.ui.dashboard_tabs.dashboard_settings_tab_widget import DashboardSettingsTabWidget

    get_qapp()
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    app_settings.user_name = "Minh"
    focus = SimpleNamespace(set_character=MagicMock(), character_changed=MagicMock(connect=MagicMock()))
    registry = SimpleNamespace(all=lambda: [], enabled=lambda: [], active=lambda: None, errors={},
                               modules_changed=MagicMock(connect=MagicMock()))
    widget = DashboardSettingsTabWidget(focus, SimpleNamespace(for_module=lambda m: None), registry)
    assert widget.txt_user_name.text() == "Minh"
    widget.txt_user_name.setText("  An  ")
    widget._on_save_settings()
    assert app_settings.user_name == "An"
