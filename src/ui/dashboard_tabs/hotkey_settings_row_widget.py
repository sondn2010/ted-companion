"""1 dòng cấu hình phím tắt: nhãn · ô bắt phím · bật/tắt · chip trạng thái · ↺ khôi phục (+ cảnh báo xung đột inline)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QKeySequenceEdit, QLabel, QPushButton, QVBoxLayout, QWidget

from src.config import settings
from src.core.hotkeys.global_hotkey_manager import GlobalHotkeyManager, hotkey_manager
from src.core.hotkeys.hotkey_action_catalog import HotkeyAction
from src.core.i18n import tr

_STATUS_KEYS = {"global": "hotkey_status_global", "app_only": "hotkey_status_app_only",
                "failed": "hotkey_status_failed", "disabled": "hotkey_status_disabled"}
_REASON_KEYS = {"enable_conflict_app": "settings_hotkey_enable_conflict_app", "conflict_app": "settings_hotkey_conflict_app", "conflict_os": "settings_hotkey_conflict_os",
                "invalid": "settings_hotkey_invalid"}


class _CaptureEdit(QKeySequenceEdit):
    """Báo focus vào/ra để Cài đặt tạm huỷ phím tắt toàn cục khi đang bắt phím (nếu không phím sẽ bị nuốt)."""
    focus_changed = Signal(bool)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focus_changed.emit(True)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focus_changed.emit(False)


def persist_hotkey_overrides(manager: GlobalHotkeyManager) -> None:
    """Ghi override hiện tại của manager vào settings.hotkeys (chỉ phần khác mặc định)."""
    settings.hotkeys = manager.overrides
    settings.save()


class HotkeySettingsRowWidget(QWidget):
    def __init__(self, action: HotkeyAction, manager: GlobalHotkeyManager = hotkey_manager, parent=None):
        super().__init__(parent)
        self.action, self._manager = action, manager
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 2, 0, 2)
        outer.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.lbl_name = QLabel()
        self.lbl_name.setObjectName("FieldLabel")
        row.addWidget(self.lbl_name, stretch=1)
        self.edit = _CaptureEdit()
        self.edit.setMaximumSequenceLength(1)
        self.edit.setClearButtonEnabled(True)
        self.edit.setMinimumWidth(170)
        self.edit.editingFinished.connect(self._on_editing_finished)
        self.edit.focus_changed.connect(lambda has_focus: manager.suspend() if has_focus else manager.resume())
        row.addWidget(self.edit)
        self.chk_enabled = QCheckBox()
        self.chk_enabled.toggled.connect(self._on_enabled_toggled)
        row.addWidget(self.chk_enabled)
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("Chip")
        self.lbl_status.setMinimumWidth(130)
        row.addWidget(self.lbl_status)
        self.btn_reset = QPushButton("↺")
        self.btn_reset.setObjectName("GhostBtn")
        self.btn_reset.setFixedWidth(34)
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        row.addWidget(self.btn_reset)
        outer.addLayout(row)
        self.lbl_warning = QLabel()
        self.lbl_warning.setObjectName("WarningLabel")
        self.lbl_warning.setWordWrap(True)
        self.lbl_warning.hide()
        outer.addWidget(self.lbl_warning)
        self.refresh()

    def refresh(self) -> None:
        """Đồng bộ UI theo trạng thái manager (không phát lại tín hiệu chỉnh sửa)."""
        m, aid = self._manager, self.action.id
        self.lbl_name.setText(tr(self.action.label_key))
        self.btn_reset.setToolTip(tr("settings_hotkey_reset_tooltip"))
        self.chk_enabled.setToolTip(tr("settings_hotkey_enable_tooltip"))
        self.edit.blockSignals(True)
        self.chk_enabled.blockSignals(True)
        self.edit.setKeySequence(QKeySequence(m.sequence(aid)))
        self.chk_enabled.setChecked(m.is_enabled(aid))
        self.edit.blockSignals(False)
        self.chk_enabled.blockSignals(False)
        self.edit.setEnabled(m.is_enabled(aid))
        status = m.status(aid)
        self.lbl_status.setText(tr(_STATUS_KEYS.get(status, "hotkey_status_disabled")))
        self.lbl_status.setProperty("status", status)

    def _show_warning(self, reason: str) -> None:
        self.lbl_warning.setText(tr(_REASON_KEYS.get(reason, "settings_hotkey_invalid")))
        self.lbl_warning.show()

    def _on_editing_finished(self) -> None:
        seq = self.edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        if not seq or seq == self._manager.sequence(self.action.id):   # xoá trống / không đổi → trả về phím hiện tại
            self.refresh()
            return
        ok, reason = self._manager.try_rebind(self.action.id, seq)
        if ok:
            self.lbl_warning.hide()
            persist_hotkey_overrides(self._manager)
        else:
            self._show_warning(reason)
            self.refresh()   # trả ô về phím cũ, phím cũ vẫn hoạt động

    def _on_enabled_toggled(self, enabled: bool) -> None:
        ok, reason = self._manager.set_enabled(self.action.id, enabled)
        if ok:
            self.lbl_warning.hide()
            persist_hotkey_overrides(self._manager)
        else:
            self._show_warning("enable_" + reason)   # vẫn tắt vì phím đang trùng hành động khác
            self.refresh()

    def _on_reset_clicked(self) -> None:
        ok, reason = self._manager.reset(self.action.id)
        persist_hotkey_overrides(self._manager)   # reset có thể đã bật lại hành động dù phím mặc định đang bị chiếm
        if ok:
            self.lbl_warning.hide()
        else:
            self._show_warning(reason)
        self.refresh()
