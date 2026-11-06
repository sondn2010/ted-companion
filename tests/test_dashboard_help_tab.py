"""Unit tests cho DashboardHelpTabWidget và tích hợp mục Trợ giúp (Help) trong Ted."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QMenu, QWidget

from src.core.focus_engine import FocusState
from src.modules_runtime.module_manifest_schema import ModuleManifest
from src.ui.companion_context_menu_builder import build_companion_context_menu
from src.ui.dashboard_tabs.dashboard_help_tab_widget import DashboardHelpTabWidget
from src.ui.dashboard_window import DashboardWindow
from tests.qt_offscreen_app_helper import get_qapp


@pytest.fixture(autouse=True)
def qapp():
    return get_qapp()


def test_help_tab_widget_initializes_with_vietnamese():
    tab = DashboardHelpTabWidget()
    assert tab.current_lang == "vi"

    # Nội dung tiếng Việt được nạp đầy đủ
    text = tab.text_browser.toPlainText()
    assert "Deep Work" in text
    assert "Pomodoro" in text
    assert "Não AI" in text
    assert "Bãi đỗ Xao nhãng" in text or "Parking Lot" in text
    assert "Leitner" in text
    assert "Rocks" in text
    assert "Markdown" not in text
    # Header hiển thị logo app; chân trang hiển thị thông tin tác giả
    assert not tab.lbl_logo.pixmap().isNull()
    assert tab.lbl_title.text() == "Cẩm nang Ted Companion"
    assert "Thông tin tác giả: Son Do" in tab.lbl_author.text()
    assert "sondn2010@gmail.com" in tab.lbl_author.text()


def test_help_tab_switch_language_to_english():
    tab = DashboardHelpTabWidget()
    tab.switch_language("en")

    assert tab.current_lang == "en"

    # Nội dung tiếng Anh được hiển thị
    text = tab.text_browser.toPlainText()
    assert "Ted Companion" in text
    assert "Deep Work" in text
    assert "Pomodoro" in text
    assert "Distraction Parking Lot" in text
    assert "AI Brain" in text
    assert "Leitner" in text
    assert "Markdown" not in text
    assert tab.lbl_title.text() == "Ted Companion Handbook"
    assert "Author: Son Do" in tab.lbl_author.text()
    assert "sondn2010@gmail.com" in tab.lbl_author.text()


def test_help_tab_follows_app_language_signal():
    from src.core.i18n import i18n
    tab = DashboardHelpTabWidget()
    i18n.language_changed.emit("en")
    assert tab.current_lang == "en"
    assert "Glossary of Terms" in tab.text_browser.toPlainText()
    i18n.language_changed.emit("vi")
    assert tab.current_lang == "vi"
    assert "Bảng Tra Cứu Thuật Ngữ" in tab.text_browser.toPlainText()


def test_help_tab_toc_links_point_to_existing_anchors():
    import re
    from src.ui.dashboard_tabs.dashboard_help_tab_widget import HELP_HTML
    for html in HELP_HTML.values():
        anchors = set(re.findall(r'<a name="([^"]+)"', html))
        links = re.findall(r'href="#([^"]+)"', html)
        assert links and all(link in anchors for link in links)


def test_help_tab_search_highlight():
    tab = DashboardHelpTabWidget()
    # Nhập từ khóa tìm kiếm
    tab.search_input.setText("Pomodoro")
    cursor = tab.text_browser.textCursor()
    assert cursor.hasSelection()
    assert cursor.selectedText() == "Pomodoro"

    # Xóa tìm kiếm → nội dung vẫn còn nguyên
    tab.search_input.setText("")
    assert "Pomodoro" in tab.text_browser.toPlainText()


def test_dashboard_window_includes_help_tab():
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

    # Help tab tồn tại trong tab widget
    assert hasattr(dash, "help_tab")
    assert dash.tabs.indexOf(dash.help_tab) != -1

    # Thứ tự tab: help_tab nằm trước settings_tab
    help_idx = dash.tabs.indexOf(dash.help_tab)
    settings_idx = dash.tabs.indexOf(dash.settings_tab)
    assert help_idx < settings_idx

    # Kiểm tra open_help()
    dash.open_help()
    assert dash.tabs.currentWidget() == dash.help_tab


def test_companion_context_menu_has_help_action():
    work = ModuleManifest(id="work", name="Công việc", icon="💼", engine="work", connection="work", enabled=True)
    help_called = []
    dashboard = SimpleNamespace(
        open_settings=lambda: None,
        open_help=lambda: help_called.append(True),
    )
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
        dashboard=dashboard,
    )

    host = QWidget()
    menu = build_companion_context_menu(QMenu(host), ctx, SimpleNamespace(open_dashboard=lambda: None, hide=lambda: None))

    actions = [a for a in menu.actions() if "Trợ giúp" in a.text()]
    assert len(actions) == 1
    actions[0].trigger()
    assert help_called == [True]


def test_tray_manager_has_help_action():
    from src.ui.tray_manager import TrayManager
    help_called = []
    dashboard = SimpleNamespace(
        refresh_all=lambda: None,
        show=lambda: None,
        raise_=lambda: None,
        activateWindow=lambda: None,
        open_help=lambda: help_called.append(True),
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
    menu = tray_mgr.tray.contextMenu()
    help_actions = [a for a in menu.actions() if "Trợ giúp" in a.text()]
    assert len(help_actions) == 1
    help_actions[0].trigger()
    assert help_called == [True]


@pytest.mark.parametrize("lang,needles", [
    ("vi", ["Hub của Ted", "Thư viện nhân vật", "Ctrl+Alt+M", "Gỡ rối ý tưởng", "Ctrl+Alt+Space", "ted-growth-hub"]),
    ("en", ["Ted Hub", "Character Gallery", "Ctrl+Alt+M", "Idea Untangling", "Ctrl+Alt+Space", "ted-growth-hub"]),
])
def test_help_covers_hub_meeting_untangle_hotkeys(lang, needles):
    tab = DashboardHelpTabWidget()
    tab.switch_language(lang)
    text = tab.text_browser.toPlainText()
    for needle in needles:
        assert needle in text
