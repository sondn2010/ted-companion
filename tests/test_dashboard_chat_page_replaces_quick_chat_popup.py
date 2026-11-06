"""Chat to nằm trong Dashboard (trang 💬), không còn popup nổi: open_for mở Dashboard đúng trang Chat."""

from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal

from tests.qt_offscreen_app_helper import get_qapp
from tests.hub_ui_test_fixtures_helper import fake_focus_engine


class _Focus(QObject):
    character_changed = Signal(str)
    current_mood = "IDLE"


def test_open_for_reveals_dashboard_chat_page(tmp_path):
    get_qapp()
    from src.config import AppConfig
    from src.modules_runtime.module_registry_loader import ModuleRegistry
    from src.ui.dashboard_window import DashboardWindow
    from src.ui.quick_chat_popup import QuickChatPopup

    chat = QuickChatPopup(_Focus(), SimpleNamespace(for_module=lambda _m: None),
                          SimpleNamespace(active=lambda: None, get=lambda _m: None))
    win = DashboardWindow(fake_focus_engine(), ModuleRegistry(AppConfig(data_dir=tmp_path), dirs=[]))
    win.bind_chat(chat)
    assert win.tabs.indexOf(chat) == 0 and not win.isVisible()

    win.tabs.setCurrentWidget(win.settings_tab)
    assert chat.open_for("work", prefill="xin chào") is True
    assert win.isVisible() and win.tabs.currentWidget() is chat
    assert chat.input_chat.text() == "xin chào"

    chat.show_hermes_nudge("GENTLE_NUDGE", "Nhắc nhẹ")   # chỉ lưu vào hội thoại, không đổi trang
    win.tabs.setCurrentWidget(win.settings_tab)
    chat.show_hermes_nudge("GENTLE_NUDGE", "Nhắc nhẹ")
    assert win.tabs.currentWidget() is win.settings_tab
    win.close()
