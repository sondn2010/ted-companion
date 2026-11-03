"""Nhóm cấu hình 🎙️ Nhận giọng nói (STT): offline (whisper.cpp tải về) hoặc máy chủ OpenAI-compatible."""

from typing import Optional

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QWidget

from src.config import settings
from src.core.background_task_spawner import spawn_background_task
from src.core.i18n import tr
from src.core.offline_voice_model_store import installed_models, resolve_model
from src.core.stt_service import stt_service
from src.ui.button_text_escape import btn_text
from src.ui.dashboard_tabs.voice_settings_group_base import (
    VoiceSettingsGroupBase,
    field_label,
    fill_local_model_combo,
    labeled,
    take_pending_or_current,
)

STT_LANGUAGES = (("vi", "Tiếng Việt"), ("en", "English"), ("auto", "Tự nhận diện / Auto"))


class SttSettingsGroupWidget(VoiceSettingsGroupBase):
    kind = "stt"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.chk_enabled.setChecked(getattr(settings, "stt_enabled", False))

        self.lbl_local_model = field_label("")
        self.combo_local_model = QComboBox()
        self.offline_layout.addLayout(labeled(self.lbl_local_model, self.combo_local_model))

        self.lbl_url = field_label("")
        self.txt_url = self.line_edit(settings.stt_server_url, "http://127.0.0.1:8881/v1")
        self.server_layout.addLayout(labeled(self.lbl_url, self.txt_url))
        row = QHBoxLayout()
        self.lbl_key = field_label("")
        self.txt_key = self.line_edit(settings.stt_api_key, "Bearer token (tùy chọn)", password=True)
        self.lbl_model = field_label("")
        self.txt_model = self.line_edit(settings.stt_model, "whisper-1")
        row.addLayout(labeled(self.lbl_key, self.txt_key), stretch=1)
        row.addLayout(labeled(self.lbl_model, self.txt_model), stretch=1)
        self.server_layout.addLayout(row)

        lang_row = QHBoxLayout()
        self.lbl_language = field_label("")
        self.combo_language = QComboBox()
        for code, name in STT_LANGUAGES:
            self.combo_language.addItem(name, code)
        idx = self.combo_language.findData(settings.stt_language or "vi")
        self.combo_language.setCurrentIndex(idx if idx >= 0 else 0)
        lang_row.addWidget(self.lbl_language)
        lang_row.addWidget(self.combo_language)
        lang_row.addStretch()
        self.extra_layout.addLayout(lang_row)

        self.btn_test = QPushButton()
        self.btn_test.clicked.connect(self._run_test)
        self.actions_row.addWidget(self.btn_test)
        self._finish_layout()

    def _field_widgets(self) -> dict:
        return {
            "stt_server_url": self.txt_url, "stt_api_key": self.txt_key, "stt_model": self.txt_model,
            "stt_language": self.combo_language, "stt_local_model": self.combo_local_model,
        }

    def refresh_offline_status(self) -> None:
        if not hasattr(self, "combo_local_model"):
            return
        current = take_pending_or_current(self.combo_local_model, settings.stt_local_model)
        fill_local_model_combo(self.combo_local_model, "stt", None, current)
        count = len(installed_models("stt"))
        self.lbl_offline_status.setText(
            tr("settings_stt_offline_ready", count=count) if count else tr("settings_stt_offline_empty"))
        self.btn_download.setText(btn_text(tr("settings_stt_download_btn")))

    def _apply_downloaded_models(self, model_ids: list) -> None:
        pending = self.combo_local_model.property("pending_id") or ""
        self.combo_local_model.setProperty("pending_id", pending if pending in model_ids else model_ids[-1])
        self.refresh_offline_status()

    def _run_test(self, *_args) -> None:
        self.set_status(tr("settings_stt_testing"))
        self.btn_test.setEnabled(False)
        if self.form_uses_offline():
            model = resolve_model("stt", self.combo_local_model.currentData() or "")
            coro = stt_service.test_offline_model(model.id if model else "")
        else:
            coro = stt_service.test_connection(
                server_url=self.txt_url.text().strip() or "http://127.0.0.1:8881/v1",
                api_key=self.txt_key.text().strip(), model=self.txt_model.text().strip() or "whisper-1",
            )

        async def _test():
            try:
                ok, msg = await coro
                self.set_status(("✅ " if ok else "❌ ") + msg, "ok" if ok else "error")
            finally:
                self.btn_test.setEnabled(True)

        spawn_background_task(_test(), "test-stt")

    def apply_to_settings(self) -> None:
        settings.stt_enabled = self.chk_enabled.isChecked()
        settings.stt_mode = self.current_mode()
        settings.stt_server_url = self.txt_url.text().strip() or "http://127.0.0.1:8881/v1"
        settings.stt_api_key = self.txt_key.text().strip()
        settings.stt_model = self.txt_model.text().strip() or "whisper-1"
        settings.stt_language = self.combo_language.currentData() or "vi"
        settings.stt_local_model = self.combo_local_model.currentData() or ""

    def retranslate_ui(self) -> None:
        self.setTitle(tr("settings_stt_group_title"))
        self.chk_enabled.setText(tr("settings_stt_enable_label"))
        self.btn_presets.setText(btn_text(tr("settings_voice_presets_btn")))
        self.lbl_local_model.setText(tr("settings_stt_local_model_label"))
        self.lbl_url.setText(tr("settings_stt_url_label"))
        self.lbl_key.setText(tr("settings_tts_key_label"))
        self.lbl_model.setText(tr("settings_stt_model_label"))
        self.lbl_language.setText(tr("settings_stt_language_label"))
        self.btn_test.setText(btn_text(tr("settings_stt_test_btn")))
        super().retranslate_ui()
