from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from src.config import APP_ICON_RELATIVE_PATH, get_resource_path, settings
from src.core.hotkeys.global_hotkey_manager import hotkey_manager
from src.core.i18n import i18n, tr
from src.ui.companion_context_menu_builder import apply_overlay_menu_window_flags
from src.ui.button_text_escape import btn_text
from src.ui.hotkey_menu_label_hint import with_hotkey_hint
from src.ui.meeting_mode.meeting_entry_point_helpers import meeting_active, request_meeting_toggle


class TrayManager:
    """Quản lý biểu tượng Ted (icon Cún Shiba cố định) trên Windows System Tray / macOS Menu Bar."""

    def __init__(self, companion_widget, dashboard_window, focus_engine, audio_manager):
        self.companion = companion_widget
        self.dashboard = dashboard_window
        self.focus_engine = focus_engine
        self.audio = audio_manager

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(QIcon(str(get_resource_path(APP_ICON_RELATIVE_PATH))))
        self._build_tray_menu()

        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        self.focus_engine.session_completed.connect(self._notify_session_completed)
        i18n.language_changed.connect(lambda _: self._build_tray_menu())
        hotkey_manager.bindings_changed.connect(self._build_tray_menu)   # gợi ý phím đổi → dựng lại menu

    def _build_tray_menu(self):
        self.tray.setToolTip(tr("tray_tooltip"))
        menu = QMenu()
        apply_overlay_menu_window_flags(menu)
        act_show_ted = QAction(with_hotkey_hint(btn_text(tr("tray_toggle_ted")), "pet.toggle"), menu)
        act_show_ted.triggered.connect(self._toggle_companion)
        menu.addAction(act_show_ted)

        act_gallery = QAction(btn_text(tr("tray_change_skin")), menu)   # 1 mục mở Bộ sưu tập nhân vật
        act_gallery.triggered.connect(self._show_character_gallery)
        menu.addAction(act_gallery)

        act_open_dash = QAction(with_hotkey_hint(btn_text(tr("tray_open_dash")), "dashboard.open"), menu)
        act_open_dash.triggered.connect(self._show_dashboard)
        menu.addAction(act_open_dash)

        if getattr(self.dashboard, "hub_tab", None) is not None:   # chỉ khi Hub đã bind
            act_hub = QAction(with_hotkey_hint(btn_text(tr("tray_hub")), "hub.open"), menu)
            act_hub.triggered.connect(self.dashboard.open_hub)
            menu.addAction(act_hub)

        act_open_help = QAction(btn_text(tr("tray_help")), menu)
        act_open_help.triggered.connect(self._show_help)
        menu.addAction(act_open_help)

        act_pomo = QAction(with_hotkey_hint(btn_text(tr("tray_pomo")), "focus.toggle"), menu)
        act_pomo.triggered.connect(self.focus_engine.pause_or_resume)
        menu.addAction(act_pomo)

        act_meeting = QAction(menu)
        act_meeting.triggered.connect(lambda checked=False: request_meeting_toggle(self.focus_engine))
        menu.addAction(act_meeting)

        def refresh_meeting_label() -> None:   # nhãn Bắt đầu ⇄ Kết thúc theo trạng thái lúc mở menu
            key = "tray_meeting_stop" if meeting_active(self.focus_engine) else "tray_meeting_start"
            act_meeting.setText(with_hotkey_hint(btn_text(tr(key)), "meeting.toggle"))
        refresh_meeting_label()
        menu.aboutToShow.connect(refresh_meeting_label)

        untangle = getattr(self.companion, "untangle_dialog", None)   # gắn bởi wire_idea_untangle (menu dựng lại khi phím tắt đổi)
        if untangle is not None:
            act_untangle = QAction(with_hotkey_hint(btn_text(tr("tray_untangle")), "untangle.open"), menu)
            act_untangle.triggered.connect(lambda checked=False: untangle.open_menu())
            menu.addAction(act_untangle)

        act_rain = QAction(btn_text(tr("tray_rain")), menu)
        act_rain.triggered.connect(lambda: self.audio.toggle_ambient())
        menu.addAction(act_rain)

        menu.addSeparator()
        act_quit = QAction(btn_text(tr("tray_quit")), menu)
        act_quit.triggered.connect(QApplication.instance().quit)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)

    def toggle_companion(self):
        if self.companion.isVisible():
            self.companion.hide()
        else:
            self.companion.show()
            self.companion.raise_()

    _toggle_companion = toggle_companion   # tên cũ giữ lại cho code/test hiện có

    def _show_dashboard(self):
        self.dashboard.refresh_all()
        self.dashboard.show()
        self.dashboard.raise_()
        self.dashboard.activateWindow()

    def _show_character_gallery(self):
        self.dashboard.open_character_gallery()

    def _show_help(self):
        if hasattr(self.dashboard, "open_help"):
            self.dashboard.open_help()
        else:
            self._show_dashboard()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_companion()

    def _notify_session_completed(self, task_title: str, mins: int, distractions: int):
        summary = ""
        if hasattr(self.focus_engine, "get_session_distractions_summary"):
            summary = self.focus_engine.get_session_distractions_summary(multiline=False)

        if distractions > 0 and summary:
            body = f"Bạn vừa tập trung {mins} phút cho '{task_title}'. Xao nhãng ({distractions} lần): {summary}. Hãy nghỉ ngơi chút nhé!"
        else:
            body = tr("tray_notify_body", mins=mins, task_title=task_title, distractions=distractions)

        self.tray.showMessage(
            tr("tray_notify_title", character=settings.character_display_name),
            body,
            QSystemTrayIcon.MessageIcon.Information,
            6000,
        )
