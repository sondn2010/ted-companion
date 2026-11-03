"""Nhóm cấu hình 🔊 Giọng nói của Ted (TTS): offline (giọng Piper tải về) hoặc máy chủ OpenAI-compatible."""

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QPushButton, QWidget

from src.config import settings
from src.core.background_task_spawner import spawn_background_task
from src.core.i18n import tr
from src.core.offline_voice_model_catalog import get_model
from src.core.offline_voice_model_store import installed_models, is_model_installed, resolve_model
from src.core.tts_service import tts_service
from src.core.vieneu_story_preprocessor.core.lexicon_mapper import export_lexicon, import_lexicon
from src.ui.button_text_escape import btn_text
from src.ui.dashboard_tabs.vieneu_voice_picker_widget import VieneuVoicePickerWidget
from src.ui.dashboard_tabs.voice_settings_group_base import (
    VoiceSettingsGroupBase,
    field_label,
    fill_local_model_combo,
    labeled,
    take_pending_or_current,
)

VI_SERVER_VOICES = ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural", "vi-VN-Standard-A", "vi-VN-Standard-B", "nova", "alloy"]
EN_SERVER_VOICES = ["en-US-AvaNeural", "en-US-AndrewNeural", "alloy", "echo", "fable", "onyx", "nova", "shimmer", "af_heart"]
TEST_TEXT_VI = "Chào bạn! Mình là Ted. Hôm nay mình cùng ôn bài nhé: x bình phương cộng hai x bằng không."
TEST_TEXT_EN = "Hello! I am Ted, your focus companion."


class TtsSettingsGroupWidget(VoiceSettingsGroupBase):
    kind = "tts"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.chk_enabled.setChecked(getattr(settings, "tts_enabled", False))

        # Offline: chọn giọng đã tải cho từng ngôn ngữ
        local_row = QHBoxLayout()
        self.lbl_local_vi = field_label("")
        self.combo_local_vi = QComboBox()
        self.lbl_local_en = field_label("")
        self.combo_local_en = QComboBox()
        local_row.addLayout(labeled(self.lbl_local_vi, self.combo_local_vi), stretch=1)
        local_row.addLayout(labeled(self.lbl_local_en, self.combo_local_en), stretch=1)
        self.offline_layout.addLayout(local_row)
        # Chọn người đọc VieNeu: chỉ hiện khi giọng Việt đang chọn là VieNeu đã tải
        self.voice_picker = VieneuVoicePickerWidget(parent=self)
        self.voice_picker.test_requested.connect(lambda: self._run_test("vi"))
        self.combo_local_vi.currentIndexChanged.connect(self._sync_voice_picker)
        self.offline_layout.addWidget(self.voice_picker)
        # Từ điển phát âm (tên riêng, từ tiếng Anh → cách đọc kiểu Việt) cho VieNeu: nhập / xuất JSON
        lexicon_row = QHBoxLayout()
        self.btn_lexicon_import = QPushButton()
        self.btn_lexicon_import.setObjectName("GhostBtn")
        self.btn_lexicon_import.clicked.connect(self._on_import_lexicon)
        self.btn_lexicon_export = QPushButton()
        self.btn_lexicon_export.setObjectName("GhostBtn")
        self.btn_lexicon_export.clicked.connect(self._on_export_lexicon)
        lexicon_row.addWidget(self.btn_lexicon_import)
        lexicon_row.addWidget(self.btn_lexicon_export)
        lexicon_row.addStretch()
        self.offline_layout.addLayout(lexicon_row)

        # Máy chủ
        self.lbl_url = field_label("")
        self.txt_url = self.line_edit(settings.tts_server_url, "http://127.0.0.1:8880/v1")
        self.server_layout.addLayout(labeled(self.lbl_url, self.txt_url))
        row = QHBoxLayout()
        self.lbl_key = field_label("")
        self.txt_key = self.line_edit(settings.tts_api_key, "Bearer token (tùy chọn)", password=True)
        self.lbl_model = field_label("")
        self.txt_model = self.line_edit(settings.tts_model, "tts-1")
        row.addLayout(labeled(self.lbl_key, self.txt_key), stretch=1)
        row.addLayout(labeled(self.lbl_model, self.txt_model), stretch=1)
        self.server_layout.addLayout(row)
        voices = QHBoxLayout()
        self.lbl_voice_vi = field_label("")
        self.combo_voice_vi = self._editable_combo(VI_SERVER_VOICES, settings.tts_voice_vi)
        self.lbl_voice_en = field_label("")
        self.combo_voice_en = self._editable_combo(EN_SERVER_VOICES, settings.tts_voice_en)
        voices.addLayout(labeled(self.lbl_voice_vi, self.combo_voice_vi), stretch=1)
        voices.addLayout(labeled(self.lbl_voice_en, self.combo_voice_en), stretch=1)
        self.server_layout.addLayout(voices)

        # Dùng chung: tốc độ + tinh chỉnh giọng nhân vật
        speed_row = QHBoxLayout()
        self.lbl_speed = field_label("")
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.5, 2.0)
        self.spin_speed.setSingleStep(0.05)
        self.spin_speed.setValue(getattr(settings, "tts_speed", 1.0))
        speed_row.addWidget(self.lbl_speed)
        speed_row.addWidget(self.spin_speed)
        speed_row.addStretch()
        self.btn_voice_profile = QPushButton()
        self.btn_voice_profile.setObjectName("GhostBtn")
        self.btn_voice_profile.clicked.connect(self._on_open_voice_profile_dialog)
        speed_row.addWidget(self.btn_voice_profile)
        self.extra_layout.addLayout(speed_row)

        self.btn_test_vi = QPushButton()
        self.btn_test_vi.clicked.connect(lambda: self._run_test("vi"))
        self.btn_test_en = QPushButton()
        self.btn_test_en.clicked.connect(lambda: self._run_test("en"))
        self.actions_row.addWidget(self.btn_test_vi)
        self.actions_row.addWidget(self.btn_test_en)
        self._finish_layout()

    def showEvent(self, event) -> None:
        # nút 🔊 trong bong bóng chat có thể vừa đổi tts_enabled → đồng bộ để Lưu không ghi đè ngược
        self.chk_enabled.setChecked(settings.tts_enabled)
        super().showEvent(event)

    @staticmethod
    def _editable_combo(items, current: str) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(items)
        combo.setCurrentText(current)
        return combo

    def _field_widgets(self) -> dict:
        return {
            "tts_server_url": self.txt_url, "tts_api_key": self.txt_key, "tts_model": self.txt_model,
            "tts_voice_vi": self.combo_voice_vi, "tts_voice_en": self.combo_voice_en, "tts_speed": self.spin_speed,
            "tts_local_voice_vi": self.combo_local_vi, "tts_local_voice_en": self.combo_local_en,
        }

    # ---------- offline ----------
    def refresh_offline_status(self) -> None:
        if not hasattr(self, "combo_local_vi"):
            return   # gọi sớm từ lớp cha trước khi ô nhập được tạo
        for combo, lang, saved in ((self.combo_local_vi, "vi", settings.tts_local_voice_vi),
                                   (self.combo_local_en, "en", settings.tts_local_voice_en)):
            fill_local_model_combo(combo, "tts", lang, take_pending_or_current(combo, saved))
        self._sync_voice_picker()
        count = len(installed_models("tts"))
        if count:
            self.lbl_offline_status.setText(tr("settings_tts_offline_ready", count=count))
        else:
            self.lbl_offline_status.setText(tr("settings_tts_offline_empty"))
        self.btn_download.setText(btn_text(tr("settings_tts_download_btn")))

    def _sync_voice_picker(self, *_args) -> None:
        model = resolve_model("tts", self.combo_local_vi.currentData() or "", "vi")
        self.voice_picker.set_model(model.id if model else "")

    def _apply_downloaded_models(self, model_ids: list) -> None:
        for combo, lang in ((self.combo_local_vi, "vi"), (self.combo_local_en, "en")):
            pending = combo.property("pending_id") or ""
            pending_model = get_model(pending)
            if pending_model is not None and is_model_installed(pending_model):
                chosen = pending
            else:
                chosen = next((mid for mid in model_ids if (m := get_model(mid)) and m.language == lang), "")
            combo.setProperty("pending_id", chosen or combo.currentData() or "")
        self.refresh_offline_status()

    # ---------- nghe thử ----------
    def _run_test(self, lang: str = "vi") -> None:
        text = TEST_TEXT_VI if lang == "vi" else TEST_TEXT_EN
        speed = round(self.spin_speed.value(), 2)
        self.voice_picker.commit()   # giọng VieNeu đang chọn (nếu có) phải vào settings trước khi engine đọc
        self.set_status(tr("settings_tts_testing"))
        self.btn_test_vi.setEnabled(False)
        self.btn_test_en.setEnabled(False)

        if self.form_uses_offline():
            combo = self.combo_local_vi if lang == "vi" else self.combo_local_en
            model = resolve_model("tts", combo.currentData() or "", lang) or resolve_model("tts", "")
            coro = tts_service.test_offline_voice(model.id if model else "", text, speed)
        else:
            voice = (self.combo_voice_vi if lang == "vi" else self.combo_voice_en).currentText().strip()
            coro = tts_service.test_connection(
                server_url=self.txt_url.text().strip() or "http://127.0.0.1:8880/v1", voice=voice or "alloy",
                test_text=text, api_key=self.txt_key.text().strip(),
                model=self.txt_model.text().strip() or "tts-1", speed=speed,
            )

        async def _test():
            try:
                ok, msg = await coro
                self.set_status(("✅ " if ok else "❌ ") + msg, "ok" if ok else "error")
            finally:
                self.btn_test_vi.setEnabled(True)
                self.btn_test_en.setEnabled(True)

        spawn_background_task(_test(), "test-tts")

    # ---------- từ điển phát âm ----------
    def _on_import_lexicon(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("settings_tts_lexicon_import_btn"), "", "JSON (*.json)")
        if not path:
            return
        try:
            count = import_lexicon(Path(path))
        except (OSError, ValueError) as exc:   # ValueError gồm cả JSON hỏng
            self.set_status(tr("settings_tts_lexicon_error", error=exc), "error")
            return
        self.set_status(tr("settings_tts_lexicon_imported", count=count), "ok")

    def _on_export_lexicon(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, tr("settings_tts_lexicon_export_btn"), "ted_lexicon.json", "JSON (*.json)")
        if not path:
            return
        try:
            count = export_lexicon(Path(path))
        except OSError as exc:
            self.set_status(tr("settings_tts_lexicon_error", error=exc), "error")
            return
        self.set_status(tr("settings_tts_lexicon_exported", count=count, path=path), "ok")

    # ---------- giọng nhân vật (tinh chỉnh chi tiết) ----------
    def _on_open_voice_profile_dialog(self):
        from src.ui.dashboard_tabs.voice_profile_dialog import VoiceProfileDialog
        dlg = VoiceProfileDialog(parent=self)
        dlg.profile_applied.connect(self._on_voice_profile_applied)
        dlg.exec()

    def _on_voice_profile_applied(self, data: dict):
        self.txt_model.setText(data.get("model", "tts-1"))
        self.combo_voice_vi.setCurrentText(data.get("voice_vi", "vi-VN-Standard-A"))
        self.combo_voice_en.setCurrentText(data.get("voice_en", "en-US-Standard-C"))
        self.spin_speed.setValue(data.get("speed", 1.0))
        self.save_requested.emit()
        self.set_status(f"✅ Đã áp dụng mẫu giọng: {data.get('voice_vi')} / {data.get('voice_en')} ({data.get('speed')}x)", "ok")

    # ---------- lưu ----------
    def apply_to_settings(self) -> None:
        settings.tts_enabled = self.chk_enabled.isChecked()
        settings.tts_configured = settings.tts_configured or settings.tts_enabled   # hiện nút 🔊 trong bong bóng chat
        settings.tts_mode = self.current_mode()
        settings.tts_server_url = self.txt_url.text().strip() or "http://127.0.0.1:8880/v1"
        settings.tts_api_key = self.txt_key.text().strip()
        settings.tts_model = self.txt_model.text().strip() or "tts-1"
        settings.tts_voice_vi = self.combo_voice_vi.currentText().strip() or "vi-VN-Standard-A"
        settings.tts_voice_en = self.combo_voice_en.currentText().strip() or "en-US-Standard-C"
        settings.tts_speed = round(self.spin_speed.value(), 2)
        settings.tts_local_voice_vi = self.combo_local_vi.currentData() or ""
        settings.tts_local_voice_en = self.combo_local_en.currentData() or ""
        self.voice_picker.commit()

    def retranslate_ui(self) -> None:
        self.setTitle(tr("settings_tts_group_title"))
        self.chk_enabled.setText(tr("settings_tts_enable_label"))
        self.btn_presets.setText(btn_text(tr("settings_voice_presets_btn")))
        self.lbl_local_vi.setText(tr("settings_tts_voice_vi_label"))
        self.lbl_local_en.setText(tr("settings_tts_voice_en_label"))
        self.lbl_url.setText(tr("settings_tts_url_label"))
        self.lbl_key.setText(tr("settings_tts_key_label"))
        self.lbl_model.setText(tr("settings_tts_model_label"))
        self.lbl_voice_vi.setText(tr("settings_tts_voice_vi_label"))
        self.lbl_voice_en.setText(tr("settings_tts_voice_en_label"))
        self.lbl_speed.setText(tr("settings_tts_speed_label"))
        self.btn_voice_profile.setText(btn_text(tr("settings_tts_character_voice_btn")))
        self.btn_lexicon_import.setText(btn_text(tr("settings_tts_lexicon_import_btn")))
        self.btn_lexicon_export.setText(btn_text(tr("settings_tts_lexicon_export_btn")))
        self.btn_test_vi.setText(btn_text(tr("settings_tts_test_vi_btn")))
        self.btn_test_en.setText(btn_text(tr("settings_tts_test_en_btn")))
        super().retranslate_ui()
