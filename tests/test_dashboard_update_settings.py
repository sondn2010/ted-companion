from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import QMessageBox
from src.config import settings
from src.core.version_config import APP_VERSION, get_default_update_url
from src.ui.dashboard_tabs.dashboard_settings_tab_widget import DashboardSettingsTabWidget
from tests.qt_offscreen_app_helper import get_qapp


@pytest.fixture(autouse=True)
def qapp(monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    return get_qapp()


def test_dashboard_settings_tab_update_controls():
    focus = SimpleNamespace(
        set_character=MagicMock(),
        character_changed=MagicMock(connect=MagicMock()),
    )
    pool = SimpleNamespace(for_module=lambda m: None)
    registry = SimpleNamespace(
        all=lambda: [],
        enabled=lambda: [],
        active=lambda: None,
        errors={},
        modules_changed=MagicMock(connect=MagicMock()),
    )

    widget = DashboardSettingsTabWidget(focus, pool, registry)

    # Kiểm tra ô nhập update_url hiển thị đúng giá trị settings
    assert hasattr(widget, "txt_update_url")
    assert widget.txt_update_url.text() == settings.update_url

    # Thử sửa URL và lưu
    test_url = "https://custom.updates.com/version.json"
    widget.txt_update_url.setText(test_url)
    widget._on_save_settings()
    assert settings.update_url == test_url

    # Thử khôi phục URL mặc định
    widget._on_reset_update_url_clicked()
    assert widget.txt_update_url.text() == get_default_update_url()
    assert settings.update_url == get_default_update_url()


def test_dashboard_settings_tab_sleep_and_exercise_controls():
    focus = SimpleNamespace(
        set_character=MagicMock(),
        character_changed=MagicMock(connect=MagicMock()),
    )
    pool = SimpleNamespace(for_module=lambda m: None)
    registry = SimpleNamespace(
        all=lambda: [],
        enabled=lambda: [],
        active=lambda: None,
        errors={},
        modules_changed=MagicMock(connect=MagicMock()),
    )

    widget = DashboardSettingsTabWidget(focus, pool, registry)

    # Kiểm tra các widget mới về Sleep & Exercise
    assert hasattr(widget, "chk_sleep_reminder")
    assert hasattr(widget, "combo_bedtime")
    assert hasattr(widget, "chk_exercise_reminder")
    assert hasattr(widget, "spin_exercise_target")

    # Thay đổi cấu hình
    widget.chk_sleep_reminder.setChecked(False)
    widget.combo_bedtime.setCurrentText("22:30")
    widget.chk_exercise_reminder.setChecked(True)
    widget.spin_exercise_target.setValue(3)

    widget._on_save_settings()

    assert settings.sleep_reminder_enabled is False
    assert settings.bedtime_target == "22:30"
    assert settings.exercise_reminder_enabled is True
    assert settings.exercise_daily_target == 3
