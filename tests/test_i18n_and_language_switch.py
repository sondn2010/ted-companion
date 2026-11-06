"""
Unit tests cho hệ thống Đa ngôn ngữ (i18n) và chuyển đổi ngôn ngữ trong Cấu hình (Settings).
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QMenu, QWidget

from src.config import AppConfig, settings
from src.core.focus_engine import FocusState
from src.core.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGE_NAMES,
    SUPPORTED_LANGUAGES,
    get_character_skins,
    i18n,
    tr,
)
from src.modules_runtime.module_manifest_schema import ModuleManifest
from src.ui.companion_context_menu_builder import build_companion_context_menu
from src.ui.dashboard_tabs.dashboard_analytics_tab_widget import DashboardAnalyticsTabWidget
from src.ui.dashboard_tabs.dashboard_journal_tab_widget import DashboardJournalTabWidget
from src.ui.dashboard_tabs.dashboard_settings_tab_widget import DashboardSettingsTabWidget
from src.ui.dashboard_tabs.dashboard_tasks_tab_widget import DashboardTasksTabWidget
from src.ui.dashboard_window import DashboardWindow
from src.ui.tray_manager import TrayManager
from tests.qt_offscreen_app_helper import get_qapp


@pytest.fixture(autouse=True)
def qapp():
    app = get_qapp()
    # Reset language to Vietnamese before each test
    settings.language = "vi"
    i18n.set_language("vi", emit_signal=False)
    yield app
    settings.language = "vi"
    i18n.set_language("vi", emit_signal=False)


def test_i18n_translation_lookup_and_fallback():
    i18n.set_language("vi")
    assert tr("tab_tasks") == "✅ Danh sách công việc"
    assert tr("tab_settings") == "⚙️ Cài đặt"

    i18n.set_language("en")
    assert tr("tab_tasks") == "✅ Tasks"
    assert tr("tab_settings") == "⚙️ Settings"

    # Formatting interpolation
    formatted = tr("settings_saved_msg", character="Ted", language="English")
    assert "Ted" in formatted and "English" in formatted

    # Fallback to key if unknown
    assert tr("non_existent_key_123") == "non_existent_key_123"


def test_character_skins_localized():
    vi_skins = get_character_skins("vi")
    en_skins = get_character_skins("en")

    assert "Mèo" in vi_skins["cat"]
    assert "Ted Cat" in en_skins["cat"]
    assert "Cú Đêm" in vi_skins["owl"]
    assert "Night Owl" in en_skins["owl"]


def test_settings_language_persistence(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    assert config.language == DEFAULT_LANGUAGE

    config.language = "en"
    config.save()

    raw = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert raw["language"] == "en"

    # Reload from disk
    config2 = AppConfig(data_dir=tmp_path)
    assert config2.language == "en"


def test_settings_tab_language_combo_and_save(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "settings_file", tmp_path / "settings.json")

    focus = SimpleNamespace(
        set_character=MagicMock(),
        tasks_updated=MagicMock(connect=MagicMock()),
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

    tab = DashboardSettingsTabWidget(focus, pool, registry)

    # Check combo has Vietnamese and English
    assert tab.combo_language.count() >= 2
    assert tab.combo_language.findData("vi") >= 0
    assert tab.combo_language.findData("en") >= 0

    # Switch to English in combo and save
    idx_en = tab.combo_language.findData("en")
    tab.combo_language.setCurrentIndex(idx_en)
    tab._on_save_settings()

    assert settings.language == "en"
    assert i18n.current_language == "en"
    assert tab.btn_save_cfg.text() == "💾 Save Settings && Timer"  # && = escape mnemonic của Qt


def test_dashboard_window_retranslates_all_tabs_and_title():
    focus = SimpleNamespace(
        tasks_updated=MagicMock(connect=MagicMock()),
        character_changed=MagicMock(connect=MagicMock()),
    )
    registry = SimpleNamespace(
        modules_changed=MagicMock(connect=MagicMock()),
        enabled=lambda: [],
        active=lambda: None,
        all=lambda: [],
        errors={},
    )
    dash = DashboardWindow(focus, registry)

    # Starts in Vietnamese
    assert "Trung tâm Điều phối" in dash.windowTitle()
    assert dash.tabs.tabText(dash.tabs.indexOf(dash.tasks_tab)) == "✅ Danh sách công việc"
    assert dash.tabs.tabText(dash.tabs.indexOf(dash.settings_tab)) == "⚙️ Cài đặt"
    assert dash.help_tab.current_lang == "vi"

    # Switch language to English
    i18n.set_language("en")

    assert "Deep Work Hub" in dash.windowTitle()
    assert dash.tabs.tabText(dash.tabs.indexOf(dash.tasks_tab)) == "✅ Tasks"
    assert dash.tabs.tabText(dash.tabs.indexOf(dash.journal_tab)) == "📔 Journal"
    assert dash.tabs.tabText(dash.tabs.indexOf(dash.analytics_tab)) == "📊 Analytics"
    assert dash.tabs.tabText(dash.tabs.indexOf(dash.help_tab)) == "❓ Help"
    assert dash.tabs.tabText(dash.tabs.indexOf(dash.settings_tab)) == "⚙️ Settings"
    assert dash.help_tab.current_lang == "en"

    # Switch back to Vietnamese
    i18n.set_language("vi")
    assert dash.tabs.tabText(dash.tabs.indexOf(dash.tasks_tab)) == "✅ Danh sách công việc"
    assert dash.help_tab.current_lang == "vi"


def test_companion_context_menu_bilingual():
    work = ModuleManifest(id="work", name="Work", icon="💼", engine="work", connection="work", enabled=True)
    ctx = SimpleNamespace(
        focus_engine=SimpleNamespace(
            state=FocusState.IDLE,
            pause_or_resume=lambda: None,
            stop_session=lambda completed=False: None,
            start_break=lambda: None,
            set_character=lambda k: None,
        ),
        registry=SimpleNamespace(active=lambda: work, enabled=lambda: [work], set_active=lambda mid: None),
        audio=SimpleNamespace(is_ambient_playing=False, toggle_ambient=lambda: None),
        engine_host=SimpleNamespace(dispatch=lambda m, a: None),
        dashboard=SimpleNamespace(open_settings=lambda: None, open_help=lambda: None),
    )

    host = QWidget()

    # Vietnamese
    i18n.set_language("vi")
    menu_vi = build_companion_context_menu(QMenu(host), ctx, SimpleNamespace(open_dashboard=lambda: None, hide=lambda: None))
    actions_vi = [a.text() for a in menu_vi.actions()]
    assert any("Bắt đầu" in a for a in actions_vi)
    assert any("Cài đặt" in a for a in actions_vi)
    assert any("Thoát" in a for a in actions_vi)

    # English
    i18n.set_language("en")
    menu_en = build_companion_context_menu(QMenu(host), ctx, SimpleNamespace(open_dashboard=lambda: None, hide=lambda: None))
    actions_en = [a.text() for a in menu_en.actions()]
    assert any("Start" in a for a in actions_en)
    assert any("Settings" in a for a in actions_en)
    assert any("Quit" in a for a in actions_en)


def test_tray_manager_menu_bilingual():
    dashboard = SimpleNamespace(
        refresh_all=lambda: None,
        show=lambda: None,
        raise_=lambda: None,
        activateWindow=lambda: None,
        open_help=lambda: None,
    )
    focus = SimpleNamespace(
        session_completed=MagicMock(connect=MagicMock()),
        character_changed=MagicMock(connect=MagicMock()),
        pause_or_resume=lambda: None,
    )
    tray_mgr = TrayManager(
        companion_widget=SimpleNamespace(isVisible=lambda: True, hide=lambda: None, show=lambda: None, raise_=lambda: None),
        dashboard_window=dashboard,
        focus_engine=focus,
        audio_manager=SimpleNamespace(toggle_ambient=lambda: None),
    )

    # Vietnamese
    i18n.set_language("vi")
    menu = tray_mgr.tray.contextMenu()
    assert any("Hiện / Ẩn" in a.text() for a in menu.actions())
    assert any("Thoát" in a.text() for a in menu.actions())

    # English
    i18n.set_language("en")
    menu = tray_mgr.tray.contextMenu()
    assert any("Show / Hide" in a.text() for a in menu.actions())
    assert any("Quit" in a.text() for a in menu.actions())


def test_tasks_and_journal_and_analytics_tabs_retranslate():
    focus = SimpleNamespace(tasks_updated=MagicMock(connect=MagicMock()))

    tasks_tab = DashboardTasksTabWidget(focus)
    journal_tab = DashboardJournalTabWidget(focus)
    analytics_tab = DashboardAnalyticsTabWidget()

    # Initial (vi)
    assert "Công việc Trọng tâm" in tasks_tab.title_lbl.text()
    assert "Nhật ký Tập trung" in journal_tab.lbl_title.text()
    assert "Deep Work Hôm nay" in analytics_tab.lbl_title.text()

    # Change language to English
    i18n.set_language("en")

    assert "Most Important Tasks" in tasks_tab.title_lbl.text()
    assert "Add a new task" in tasks_tab.btn_add.toolTip()
    assert "Focus Journal" in journal_tab.lbl_title.text()
    assert "Save Journal" in journal_tab.btn_save_journal.text()
    assert "Deep Work Status" in analytics_tab.lbl_title.text()
    assert "Completed Pomodoros" in analytics_tab.lbl_t_sessions.text()


def test_companion_widget_pomodoro_buttons_bilingual():
    from src.core.focus_engine import FocusEngine
    from src.ui.companion_widget import TedCompanionWidget

    focus = FocusEngine(audio_manager=SimpleNamespace(play_chime=lambda: None, toggle_ambient=lambda: None, is_ambient_playing=False))
    ctx = SimpleNamespace(
        focus_engine=focus,
        quick_chat=SimpleNamespace(show_mindful_ping=lambda t: None, show_hermes_nudge=lambda m, s: None),
        bubble=None,
    )
    widget = TedCompanionWidget(ctx, cheer_provider=SimpleNamespace(show_cheer=lambda: None))
    widget.show()

    # Vietnamese
    i18n.set_language("vi")
    assert widget.btn_pomo_action.text() == "▶"
    assert "Bắt đầu" in widget.btn_pomo_action.toolTip()

    # English
    i18n.set_language("en")
    assert widget.btn_pomo_action.text() == "▶"
    assert "Start" in widget.btn_pomo_action.toolTip()

    # Running state in English
    focus.pause_or_resume()
    assert widget.btn_pomo_action.text() == "⏸"
    assert "Pause" in widget.btn_pomo_action.toolTip()
    assert widget.btn_pomo_stop.text() == "⏹"
    assert "Stop" in widget.btn_pomo_stop.toolTip()

    # Switch back to Vietnamese while running
    i18n.set_language("vi")
    assert widget.btn_pomo_action.text() == "⏸"
    assert "Tạm dừng" in widget.btn_pomo_action.toolTip()
    assert widget.btn_pomo_stop.text() == "⏹"
    assert "Kết thúc" in widget.btn_pomo_stop.toolTip()

    focus.stop_session(completed=False)

