"""Card "⌨️ Phím tắt": mỗi hành động khả dụng 1 dòng; "Khôi phục tất cả" ở chân card."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QVBoxLayout, QWidget

from src.config import settings
from src.core.hotkeys.global_hotkey_manager import GlobalHotkeyManager, hotkey_manager
from src.core.hotkeys.hotkey_action_catalog import HOTKEY_ACTIONS
from src.core.i18n import i18n, tr
from src.ui.button_text_escape import btn_text
from src.ui.dashboard_tabs.hotkey_settings_row_widget import HotkeySettingsRowWidget, persist_hotkey_overrides


class HotkeySettingsGroupWidget(QWidget):
    def __init__(self, manager: GlobalHotkeyManager = hotkey_manager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._rows: list[HotkeySettingsRowWidget] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("SectionLabel")
        layout.addWidget(self.lbl_title)
        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("HintLabel")
        self.lbl_hint.setWordWrap(True)
        layout.addWidget(self.lbl_hint)
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(0)
        layout.addLayout(self.rows_layout)
        self.btn_reset_all = QPushButton()
        self.btn_reset_all.setObjectName("GhostBtn")
        self.btn_reset_all.clicked.connect(self._on_reset_all)
        layout.addWidget(self.btn_reset_all, alignment=Qt.AlignmentFlag.AlignLeft)
        self.chk_untangle_nudge = QCheckBox()   # bật/tắt duy nhất của nudge Gỡ Rối thích nghi
        self.chk_untangle_nudge.setChecked(bool(settings.untangle_nudge_enabled))
        self.chk_untangle_nudge.toggled.connect(self._on_untangle_nudge_toggled)
        layout.addWidget(self.chk_untangle_nudge)
        self.chk_health_break = QCheckBox()   # bật/tắt duy nhất của gợi ý vận động nhẹ sau phiên Deep Work
        self.chk_health_break.setChecked(bool(settings.health_break_prompt_enabled))
        self.chk_health_break.toggled.connect(self._on_health_break_toggled)
        layout.addWidget(self.chk_health_break)
        self._rebuild_rows()
        self.retranslate_ui()
        manager.bindings_changed.connect(self._on_bindings_changed)
        i18n.language_changed.connect(lambda _lang: self.retranslate_ui())

    def _available_ids(self) -> list[str]:
        return [a.id for a in HOTKEY_ACTIONS if self._manager.is_available(a.id)]

    def _rebuild_rows(self) -> None:
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        for action in HOTKEY_ACTIONS:
            if self._manager.is_available(action.id):
                row = HotkeySettingsRowWidget(action, self._manager)
                self.rows_layout.addWidget(row)
                self._rows.append(row)

    def _on_bindings_changed(self) -> None:
        # Chỉ dựng lại khi tập hành động khả dụng đổi (vd. Hub vừa gắn); còn lại refresh tại chỗ để không phá dòng đang sửa
        if [r.action.id for r in self._rows] != self._available_ids():
            self._rebuild_rows()
        for row in self._rows:
            row.refresh()

    def _on_reset_all(self) -> None:
        self._manager.apply({})
        persist_hotkey_overrides(self._manager)

    def _on_untangle_nudge_toggled(self, enabled: bool) -> None:
        settings.untangle_nudge_enabled = enabled
        settings.save()

    def _on_health_break_toggled(self, enabled: bool) -> None:
        settings.health_break_prompt_enabled = enabled
        settings.save()

    def retranslate_ui(self) -> None:
        self.chk_health_break.setText(tr("settings_health_break_prompt_enabled"))
        self.chk_untangle_nudge.setText(tr("settings_untangle_nudge_enabled"))
        self.lbl_title.setText(tr("settings_hotkeys_group_title"))
        hint = tr("settings_hotkeys_hint")
        if sys.platform == "darwin":
            hint += " " + tr("settings_hotkeys_mac_note")
        self.lbl_hint.setText(hint)
        self.btn_reset_all.setText(btn_text(tr("settings_hotkey_reset_all")))
        for row in self._rows:
            row.refresh()
