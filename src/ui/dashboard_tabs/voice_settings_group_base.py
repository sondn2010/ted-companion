"""Khung chung cho nhóm cấu hình TTS / STT trong tab Cài đặt (DRY giữa 2 nhóm).

Bố cục người dùng phổ thông nhìn thấy (từ trên xuống):
  [x] Bật …                    [✨ Chọn cấu hình mẫu…]  (popup tìm kiếm ~20 mẫu → điền sẵn mọi ô)
  Chạy bằng: [Tự động | Trên máy (offline) | Máy chủ]
  ── 💻 Offline ──  trạng thái mô hình · chọn mô hình đã tải · [⬇️ Tải mô hình offline…]
  ── 🌐 Máy chủ ──  URL · API key · model …
  [Nghe thử / Chạy thử] [💾 Lưu]   dòng trạng thái

Lớp con khai báo ô nhập riêng và hiện thực `_field_widgets()`, `_apply_downloaded_models()`, `_run_test()`.
"""

from html import escape
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config import settings
from src.core.i18n import tr
from src.core.offline_voice_model_catalog import get_model
from src.core.offline_voice_model_store import installed_models, is_model_installed
from src.core.voice_config_presets import VoiceConfigPreset
from src.ui.button_text_escape import btn_text
from src.ui.theme import design_tokens as tk

MODES = ("auto", "embedded", "server")


def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label


def labeled(label: QLabel, widget: QWidget) -> QVBoxLayout:
    box = QVBoxLayout()
    box.setSpacing(4)
    box.addWidget(label)
    box.addWidget(widget)
    return box


def fill_local_model_combo(combo: QComboBox, kind: str, language: Optional[str], current_id: str) -> None:
    """Combo các model ĐÃ TẢI (+ mục 'Tự chọn'); giữ lựa chọn hiện tại nếu còn."""
    combo.blockSignals(True)
    combo.clear()
    combo.addItem(tr("settings_local_auto_pick"), "")
    for model in installed_models(kind, language):
        combo.addItem(model.title, model.id)
    idx = combo.findData(current_id)
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)


def take_pending_or_current(combo: QComboBox, saved_id: str) -> str:
    """Id cần chọn lại sau khi nạp lại combo: model preset/tải-về đang chờ (nếu đã có) > lựa chọn hiện tại > đã lưu."""
    pending = combo.property("pending_id") or ""
    model = get_model(pending) if pending else None
    if model is not None and is_model_installed(model):
        combo.setProperty("pending_id", "")
        return pending
    if combo.count():
        return combo.currentData() or ""
    return saved_id


class VoiceSettingsGroupBase(QGroupBox):
    save_requested = Signal()

    kind = "tts"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._download_dialog = None
        root = QVBoxLayout(self)
        root.setSpacing(10)

        top = QHBoxLayout()
        self.chk_enabled = QCheckBox()
        top.addWidget(self.chk_enabled)
        top.addStretch()
        self.btn_presets = QPushButton()
        self.btn_presets.setObjectName("PrimaryBtn")
        self.btn_presets.clicked.connect(self.open_preset_picker)
        top.addWidget(self.btn_presets)
        root.addLayout(top)

        mode_row = QHBoxLayout()
        self.lbl_mode = field_label("")
        mode_row.addWidget(self.lbl_mode)
        self.combo_mode = QComboBox()
        for mode in MODES:
            self.combo_mode.addItem("", mode)
        self.combo_mode.currentIndexChanged.connect(self._update_panels)
        mode_row.addWidget(self.combo_mode, stretch=1)
        root.addLayout(mode_row)

        # --- Khối offline ---
        self.offline_panel = QFrame()
        self.offline_panel.setObjectName("Card")
        self.offline_layout = QVBoxLayout(self.offline_panel)
        self.offline_layout.setContentsMargins(14, 10, 14, 10)
        self.lbl_offline_title = QLabel()
        self.lbl_offline_title.setObjectName("SectionLabel")
        self.offline_layout.addWidget(self.lbl_offline_title)
        self.lbl_offline_status = QLabel()
        self.lbl_offline_status.setWordWrap(True)
        self.offline_layout.addWidget(self.lbl_offline_status)
        self.btn_download = QPushButton()
        self.btn_download.clicked.connect(lambda: self.open_download_dialog())
        root.addWidget(self.offline_panel)

        # --- Khối máy chủ ---
        self.server_panel = QFrame()
        self.server_panel.setObjectName("Card")
        self.server_layout = QVBoxLayout(self.server_panel)
        self.server_layout.setContentsMargins(14, 10, 14, 10)
        self.lbl_server_title = QLabel()
        self.lbl_server_title.setObjectName("SectionLabel")
        self.server_layout.addWidget(self.lbl_server_title)
        root.addWidget(self.server_panel)

        self.extra_layout = QVBoxLayout()   # ô dùng chung cho cả 2 chế độ (tốc độ đọc, ngôn ngữ…)
        root.addLayout(self.extra_layout)

        self.actions_row = QHBoxLayout()
        self.btn_save = QPushButton()
        self.btn_save.setObjectName("PrimaryBtn")
        self.btn_save.clicked.connect(self.save_requested)
        root.addLayout(self.actions_row)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

    # ---------- tiện ích cho lớp con ----------
    def _finish_layout(self) -> None:
        self.offline_layout.addWidget(self.btn_download)
        self.actions_row.addWidget(self.btn_save)
        self.actions_row.addStretch()
        self.set_mode(getattr(settings, f"{self.kind}_mode", "auto"))
        self.retranslate_ui()

    def line_edit(self, value: str, placeholder: str = "", password: bool = False) -> QLineEdit:
        edit = QLineEdit(value)
        edit.setPlaceholderText(placeholder)
        if password:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        return edit

    def set_mode(self, mode: str) -> None:
        idx = self.combo_mode.findData(mode)
        self.combo_mode.setCurrentIndex(idx if idx >= 0 else 0)
        self._update_panels()

    def current_mode(self) -> str:
        return self.combo_mode.currentData() or "auto"

    def form_uses_offline(self) -> bool:
        """Chế độ thực tế theo FORM (chưa lưu): auto → offline nếu đã tải model."""
        mode = self.current_mode()
        return mode == "embedded" or (mode == "auto" and bool(installed_models(self.kind)))

    def _update_panels(self, *_args) -> None:
        mode = self.current_mode()
        self.offline_panel.setVisible(mode in ("auto", "embedded"))
        self.server_panel.setVisible(mode in ("auto", "server"))
        self.refresh_offline_status()

    def set_status(self, text: str, tone: str = "info") -> None:
        color = {"ok": tk.TERTIARY, "error": tk.ERROR, "warn": tk.WARNING, "info": tk.TEXT_MUTED}[tone]
        # escape: lỗi từ máy chủ / piper / whisper là văn bản bên ngoài, không được diễn giải thành HTML
        self.lbl_status.setText(f"<span style='color:{color};'>{escape(text)}</span>")

    # ---------- preset ----------
    def open_preset_picker(self):
        from src.ui.dashboard_tabs.voice_preset_picker_dialog import VoicePresetPickerDialog
        dialog = VoicePresetPickerDialog(self.kind, parent=self)
        dialog.preset_chosen.connect(self.apply_preset)
        dialog.open()
        return dialog

    def apply_preset(self, preset: VoiceConfigPreset) -> None:
        """Điền giá trị preset vào ô nhập (chưa lưu). Thiếu model offline → hỏi tải ngay."""
        from src.ui.dashboard_tabs.voice_preset_picker_dialog import missing_models
        widgets = self._field_widgets()
        for key, value in preset.values.items():
            if key == f"{self.kind}_mode":
                self.set_mode(value)
                continue
            widget = widgets.get(key)
            if isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, QComboBox):
                idx = widget.findData(value)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
                elif widget.isEditable():
                    widget.setCurrentText(str(value))
                else:   # model offline chưa tải: nhớ lại để chọn sau khi tải xong
                    widget.setProperty("pending_id", value)
        self.chk_enabled.setChecked(True)
        hint = tr("settings_voice_prefilled", name=preset.title)
        if preset.needs_api_key and not widgets[f"{self.kind}_api_key"].text().strip():
            hint += " " + tr("settings_voice_need_api_key")
            widgets[f"{self.kind}_api_key"].setFocus()
        self.set_status(hint, "ok")
        missing = missing_models(preset)
        if missing:
            total = sum(m.size_mb for m in missing)
            answer = QMessageBox.question(
                self, tr("settings_voice_need_download_title"),
                tr("settings_voice_need_download_msg", names=", ".join(m.title for m in missing), size=total),
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.open_download_dialog([m.id for m in missing])

    # ---------- tải model ----------
    def open_download_dialog(self, preselect_ids=()):
        from src.ui.dashboard_tabs.offline_voice_model_download_dialog import OfflineVoiceModelDownloadDialog
        if self._download_dialog is not None and self._download_dialog.isVisible():
            self._download_dialog.raise_()   # đang mở / đang tải: không mở popup thứ 2 tải chồng
            return self._download_dialog
        dialog = OfflineVoiceModelDownloadDialog(self.kind, preselect_ids, parent=self)
        dialog.models_ready.connect(self._on_models_ready)
        dialog.test_requested.connect(self._run_test)
        dialog.finished.connect(lambda _r: self.refresh_offline_status())
        self._download_dialog = dialog
        dialog.open()   # không chặn vòng lặp asyncio trong lúc tải
        return dialog

    def _on_models_ready(self, model_ids: list) -> None:
        self.set_mode("embedded")
        self.chk_enabled.setChecked(True)
        self._apply_downloaded_models(model_ids)
        self.set_status(tr("settings_voice_downloaded_prefilled"), "ok")

    # ---------- lớp con hiện thực ----------
    def _field_widgets(self) -> dict:
        raise NotImplementedError

    def _apply_downloaded_models(self, model_ids: list) -> None:
        raise NotImplementedError

    def refresh_offline_status(self) -> None:
        raise NotImplementedError

    def _run_test(self) -> None:
        raise NotImplementedError

    def retranslate_ui(self) -> None:
        self.combo_mode.setItemText(0, tr("settings_voice_mode_auto"))
        self.combo_mode.setItemText(1, tr("settings_voice_mode_embedded"))
        self.combo_mode.setItemText(2, tr("settings_voice_mode_server"))
        self.lbl_mode.setText(tr("settings_voice_mode_label"))
        self.lbl_offline_title.setText(tr("settings_voice_offline_title"))
        self.lbl_server_title.setText(tr("settings_voice_server_title"))
        self.btn_save.setText(btn_text(tr("settings_voice_save_btn")))
        self.refresh_offline_status()
