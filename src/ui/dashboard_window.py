import logging
from typing import Optional

from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget
from src.bridge.hermes_client_pool import hermes_client_pool
from src.config import settings
from src.core.i18n import i18n, tr
from src.ui.dashboard_tabs.character_gallery_tab_widget import CharacterGalleryTabWidget
from src.ui.dashboard_tabs.dashboard_analytics_tab_widget import DashboardAnalyticsTabWidget
from src.ui.dashboard_tabs.dashboard_help_tab_widget import DashboardHelpTabWidget
from src.ui.dashboard_tabs.dashboard_hub_tab_widget import DashboardHubTab
from src.ui.dashboard_tabs.dashboard_journal_tab_widget import DashboardJournalTabWidget
from src.ui.dashboard_tabs.dashboard_settings_tab_widget import DashboardSettingsTabWidget
from src.ui.dashboard_tabs.dashboard_tasks_tab_widget import DashboardTasksTabWidget
from src.ui.dashboard_sidebar_navigation import SidebarNavigation

logger = logging.getLogger("ted")


class DashboardWindow(QMainWindow):
    """
    Vỏ cửa sổ quản lý (sidebar + trang, xem SidebarNavigation): tab core luôn có (Tasks, Journal, Analytics) + 1 tab cho mỗi module đang chạy
    (engine.build_dashboard_tab()) + Trợ giúp + Cài đặt (luôn cuối). Chỉ tab module được dựng lại khi modules_changed.
    """

    def __init__(self, focus_engine, registry, parent=None):
        super().__init__(parent)
        self.focus_engine = focus_engine
        self._registry = registry
        self._host = None
        self._module_tabs: list[QWidget] = []
        self._built_engine_ids: tuple[str, ...] = ()
        self.hub_tab: Optional[DashboardHubTab] = None   # dựng ở bind_gamification (không có Hub → không có trang)
        self.chat_tab: Optional[QWidget] = None   # trang Chat to (QuickChatPopup), gắn ở bind_chat
        self.setWindowTitle(tr("dashboard_title"))
        self.resize(1080, 700)

        central = QWidget(self)
        central.setObjectName("DashboardRoot")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = SidebarNavigation(settings.character_display_name, self)
        self.tasks_tab = DashboardTasksTabWidget(focus_engine)
        self.journal_tab = DashboardJournalTabWidget(focus_engine)
        self.analytics_tab = DashboardAnalyticsTabWidget()
        self.gallery_tab = CharacterGalleryTabWidget(focus_engine)
        self.help_tab = DashboardHelpTabWidget()
        self.settings_tab = DashboardSettingsTabWidget(focus_engine, hermes_client_pool, registry)
        self.tabs.addTab(self.tasks_tab, tr("tab_tasks"))
        self.tabs.addTab(self.journal_tab, tr("tab_journal"))
        self.tabs.addTab(self.analytics_tab, tr("tab_analytics"))
        self.tabs.addTab(self.gallery_tab, tr("tab_characters"))
        self.tabs.addTab(self.help_tab, tr("tab_help"))
        self.tabs.addTab(self.settings_tab, tr("tab_settings"))
        main_layout.addWidget(self.tabs)

        self.tasks_tab.data_changed.connect(self.refresh_all)
        focus_engine.tasks_updated.connect(self.refresh_all)
        self.settings_tab.open_gallery_requested.connect(self.open_character_gallery)
        focus_engine.character_changed.connect(lambda *_: self._sync_brand())
        i18n.language_changed.connect(self._on_language_changed)

        # Đồng bộ ngôn ngữ khởi đầu cho Help tab
        if hasattr(self.help_tab, "switch_language") and settings.language != self.help_tab.current_lang:
            self.help_tab.switch_language(settings.language)

        self.refresh_all()

    def _on_language_changed(self, lang: str):
        self.retranslate_ui()
        if hasattr(self.help_tab, "switch_language"):
            self.help_tab.switch_language(lang)

    def _sync_brand(self):
        # Tên nhân vật trên sidebar phụ thuộc skin + ngôn ngữ
        self.tabs.brand_label.setText(settings.character_display_name)

    def retranslate_ui(self):
        self.setWindowTitle(tr("dashboard_title"))
        self._sync_brand()
        self.tabs.setTabText(self.tabs.indexOf(self.tasks_tab), tr("tab_tasks"))
        self.tabs.setTabText(self.tabs.indexOf(self.journal_tab), tr("tab_journal"))
        self.tabs.setTabText(self.tabs.indexOf(self.analytics_tab), tr("tab_analytics"))
        if self.hub_tab is not None:
            self.tabs.setTabText(self.tabs.indexOf(self.hub_tab), tr("tab_hub"))
        if self.chat_tab is not None:
            self.tabs.setTabText(self.tabs.indexOf(self.chat_tab), tr("tab_chat"))
        self.tabs.setTabText(self.tabs.indexOf(self.gallery_tab), tr("tab_characters"))
        self.tabs.setTabText(self.tabs.indexOf(self.help_tab), tr("tab_help"))
        self.tabs.setTabText(self.tabs.indexOf(self.settings_tab), tr("tab_settings"))

    def bind_modules(self, engine_host):
        """Gọi sau khi host.sync đã nối vào modules_changed (để engine mới sẵn sàng trước khi dựng tab)."""
        self._host = engine_host
        self._registry.modules_changed.connect(self.rebuild_module_tabs)
        self.rebuild_module_tabs()

    def rebuild_module_tabs(self):
        # Chỉ dựng lại khi tập/thứ tự engine đổi; đổi module chính không được xoá chữ đang nhập dở trong tab
        engine_ids = tuple(self._host.engines) if self._host is not None else ()
        if engine_ids == self._built_engine_ids and self._host is not None:
            return
        self._built_engine_ids = engine_ids
        for tab in self._module_tabs:
            self.tabs.removeTab(self.tabs.indexOf(tab))
            tab.deleteLater()
        self._module_tabs = []
        if self._host is None:
            return
        anchor = getattr(self, "help_tab", self.settings_tab)
        insert_at = self.tabs.indexOf(anchor)  # Module chèn trước Trợ giúp & Cài đặt
        for engine in self._host.engines.values():
            try:
                tab = engine.build_dashboard_tab()
            except Exception:
                logger.exception("Module %s lỗi khi dựng tab Dashboard", engine.manifest.id)
                continue
            if tab is None:
                continue
            title = f"{engine.manifest.icon} {engine.manifest.name}".strip()
            self.tabs.insertTab(insert_at, tab, title)
            self._module_tabs.append(tab)
            insert_at += 1

    def bind_chat(self, chat) -> None:
        """Gắn khung chat (QuickChatPopup) làm trang đầu tiên; chat cần hiện (double-click avatar, hotkey, coach...) → mở trang này."""
        self.chat_tab = chat
        self.tabs.insertTab(0, chat, tr("tab_chat"))
        chat.reveal_requested.connect(self.open_chat)

    def open_chat(self):
        if self.chat_tab is None:
            return
        self.tabs.setCurrentWidget(self.chat_tab)
        self.show()
        self.raise_()
        self.activateWindow()
        self.chat_tab.input_chat.setFocus()

    def open_settings(self):
        self.refresh_all()
        self.tabs.setCurrentWidget(self.settings_tab)
        self.show()
        self.raise_()
        self.activateWindow()

    def open_tasks_list(self, task_id: Optional[str] = None):
        """Mở tab Công việc ở chế độ Danh sách (Bãi đỗ nằm chung trong đó), chọn sẵn task_id nếu có."""
        self.refresh_all()
        self.tabs.setCurrentWidget(self.tasks_tab)
        self.tasks_tab.show_list(task_id)
        self.show()
        self.raise_()
        self.activateWindow()

    def bind_gamification(self, service) -> None:
        """Nối Hub service cho trang Nhân vật (tiến độ mở khoá) + dựng trang Hub (sau Analytics); gọi từ main.py."""
        self.gallery_tab.bind_gamification(service)
        if self.hub_tab is None:
            self.hub_tab = DashboardHubTab()
            self.hub_tab.gallery_requested.connect(lambda: self.open_character_gallery())
            self.tabs.insertTab(self.tabs.indexOf(self.analytics_tab) + 1, self.hub_tab, tr("tab_hub"))
        self.hub_tab.bind_service(service)

    def open_hub(self):
        """Mở trang Hub (chip level trên pet / menu / tray / phím tắt); chưa có Hub → chỉ mở Dashboard."""
        if self.hub_tab is not None:
            self.tabs.setCurrentWidget(self.hub_tab)
            self.hub_tab.on_opened()
        self.show()
        self.raise_()
        self.activateWindow()

    def open_character_gallery(self, character_key: Optional[str] = None):
        """Mở trang Bộ sưu tập nhân vật (menu chuột phải / tray / Cài đặt), chọn sẵn nhân vật nếu có."""
        self.tabs.setCurrentWidget(self.gallery_tab)
        self.gallery_tab.refresh()
        if character_key:
            self.gallery_tab.select_character(character_key)
        self.show()
        self.raise_()
        self.activateWindow()

    def open_help(self):
        self.refresh_all()
        self.tabs.setCurrentWidget(self.help_tab)
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh_all(self):
        self.tasks_tab.refresh()
        self.journal_tab.refresh()
        self.analytics_tab.refresh()
        for tab in self._module_tabs:
            if hasattr(tab, "refresh") and callable(tab.refresh):
                try:
                    tab.refresh()
                except Exception:
                    logger.exception("Lỗi khi refresh tab module")
