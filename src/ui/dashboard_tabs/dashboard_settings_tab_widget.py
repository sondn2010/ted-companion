from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from src.config import USER_NAME_MAX_LEN, settings
from src.core.background_task_spawner import spawn_background_task
from src.core.i18n import (
    LANGUAGE_NAMES,
    SUPPORTED_LANGUAGES,
    i18n,
    tr,
)
from src.core.update_manager import update_manager
from src.core.version_config import APP_VERSION, get_default_update_url
from src.ui.button_text_escape import btn_text
from src.ui.dashboard_tabs.database_sync_settings_group_widget import DatabaseSyncSettingsGroupWidget
from src.ui.dashboard_tabs.hermes_connections_settings_widget import HermesConnectionsSettingsWidget
from src.ui.dashboard_tabs.hotkey_settings_group_widget import HotkeySettingsGroupWidget
from src.ui.dashboard_tabs.modules_toggle_settings_widget import ModulesToggleSettingsWidget
from src.ui.dashboard_tabs.stt_settings_group_widget import SttSettingsGroupWidget
from src.ui.dashboard_tabs.tts_settings_group_widget import TtsSettingsGroupWidget


def _card_layout(parent_layout: QVBoxLayout) -> QVBoxLayout:
    """Tạo Card (L2, bo 16px) gắn vào parent_layout; trả về layout nội dung của card."""
    card = QFrame()
    card.setObjectName("Card")
    inner = QVBoxLayout(card)
    inner.setContentsMargins(20, 16, 20, 16)
    inner.setSpacing(8)
    parent_layout.addWidget(card)
    return inner


class DashboardSettingsTabWidget(QScrollArea):
    """Tab Cài đặt: (a) ngôn ngữ, nhân vật + timer, (b) TTS/STT offline hoặc máy chủ, (c) kết nối Hermes, (d) module."""

    open_gallery_requested = Signal()   # DashboardWindow nối tới open_character_gallery

    def __init__(self, focus_engine, pool, registry, parent=None):
        super().__init__(parent)
        self.focus_engine = focus_engine
        self.setWidgetResizable(True)
        page = QWidget()
        self.setWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        self.lbl_title = QLabel(tr("settings_title"))
        self.lbl_title.setObjectName("TitleLabel")
        layout.addWidget(self.lbl_title)

        # Card chung: ngôn ngữ, nhân vật, timer, nút lưu
        general = _card_layout(layout)

        # 0. Tên người dùng (Ted gọi bạn bằng tên này)
        self.lbl_user_name = QLabel(tr("user_name_label"))
        self.lbl_user_name.setObjectName("FieldLabel")
        general.addWidget(self.lbl_user_name)
        self.txt_user_name = QLineEdit(settings.user_name)
        self.txt_user_name.setMaxLength(USER_NAME_MAX_LEN)
        general.addWidget(self.txt_user_name)

        # 1. Chọn ngôn ngữ hiển thị
        self.lbl_language = QLabel(tr("settings_language_label"))
        self.lbl_language.setObjectName("FieldLabel")
        general.addWidget(self.lbl_language)
        self.combo_language = QComboBox()
        for code in SUPPORTED_LANGUAGES:
            self.combo_language.addItem(LANGUAGE_NAMES.get(code, code), code)
        self.sync_language_combo(settings.language)
        self.combo_language.currentIndexChanged.connect(self._on_language_combo_changed)
        general.addWidget(self.combo_language)

        # 2. Chọn nhân vật Chibi
        self.lbl_character = QLabel(tr("settings_character_label"))
        self.lbl_character.setObjectName("FieldLabel")
        general.addWidget(self.lbl_character)
        # Nhiều nhân vật (có khoá/mở dần) → chọn trong trang Bộ sưu tập thay vì combo dài
        self.btn_open_gallery = QPushButton(btn_text(tr("settings_open_gallery_btn")))
        self.btn_open_gallery.clicked.connect(lambda: self.open_gallery_requested.emit())
        general.addWidget(self.btn_open_gallery)

        # 3. Thời lượng timers
        timers_row = QHBoxLayout()
        timers_row.setSpacing(8)
        self.lbl_default_pomo = QLabel(tr("settings_pomo_mins"))
        self.lbl_default_pomo.setObjectName("FieldLabel")
        timers_row.addWidget(self.lbl_default_pomo)
        self.spin_default_pomo = QSpinBox()
        self.spin_default_pomo.setRange(5, 120)
        self.spin_default_pomo.setValue(settings.default_pomodoro_mins)
        timers_row.addWidget(self.spin_default_pomo)

        self.lbl_ping_mins = QLabel(tr("settings_ping_mins"))
        self.lbl_ping_mins.setObjectName("FieldLabel")
        timers_row.addWidget(self.lbl_ping_mins)
        self.spin_ping_mins = QSpinBox()
        self.spin_ping_mins.setRange(5, 60)
        self.spin_ping_mins.setValue(settings.mindful_ping_mins)
        timers_row.addWidget(self.spin_ping_mins)
        timers_row.addStretch()
        general.addLayout(timers_row)

        # 4. Nhắc nhở giấc ngủ & làm việc muộn
        self.chk_sleep_reminder = QCheckBox(tr("settings_sleep_reminder_enabled"))
        self.chk_sleep_reminder.setChecked(bool(settings.sleep_reminder_enabled))
        general.addWidget(self.chk_sleep_reminder)

        bedtime_row = QHBoxLayout()
        bedtime_row.setSpacing(8)
        self.lbl_bedtime = QLabel(tr("settings_bedtime_label"))
        self.lbl_bedtime.setObjectName("FieldLabel")
        bedtime_row.addWidget(self.lbl_bedtime)
        self.combo_bedtime = QComboBox()
        common_times = ["21:30", "22:00", "22:30", "23:00", "23:30", "00:00", "00:30", "01:00"]
        for t in common_times:
            self.combo_bedtime.addItem(t)
        cur_bedtime = str(settings.bedtime_target or "23:00")
        if cur_bedtime not in common_times:
            self.combo_bedtime.addItem(cur_bedtime)
        idx = self.combo_bedtime.findText(cur_bedtime)
        if idx >= 0:
            self.combo_bedtime.setCurrentIndex(idx)
        bedtime_row.addWidget(self.combo_bedtime)
        bedtime_row.addStretch()
        general.addLayout(bedtime_row)

        # 5. Nhắc nhở tập thể dục tại chỗ sau Deep Work
        self.chk_exercise_reminder = QCheckBox(tr("settings_exercise_reminder_enabled"))
        self.chk_exercise_reminder.setChecked(bool(settings.exercise_reminder_enabled))
        general.addWidget(self.chk_exercise_reminder)

        exercise_row = QHBoxLayout()
        exercise_row.setSpacing(8)
        self.lbl_exercise_target = QLabel(tr("settings_exercise_target_label"))
        self.lbl_exercise_target.setObjectName("FieldLabel")
        exercise_row.addWidget(self.lbl_exercise_target)
        self.spin_exercise_target = QSpinBox()
        self.spin_exercise_target.setRange(1, 10)
        self.spin_exercise_target.setValue(getattr(settings, "exercise_daily_target", 4))
        exercise_row.addWidget(self.spin_exercise_target)
        exercise_row.addStretch()
        general.addLayout(exercise_row)

        self.btn_save_cfg = QPushButton(btn_text(tr("settings_btn_save")))
        self.btn_save_cfg.setObjectName("PrimaryBtn")
        self.btn_save_cfg.clicked.connect(self._on_save_settings)
        general.addSpacing(4)
        general.addWidget(self.btn_save_cfg, alignment=Qt.AlignmentFlag.AlignLeft)

        # 4. Giọng nói (TTS) + Nhận giọng nói (STT): offline tải về hoặc máy chủ, có popup cấu hình mẫu
        self.group_tts = TtsSettingsGroupWidget()
        self.group_tts.save_requested.connect(self._on_save_settings)
        layout.addWidget(self.group_tts)
        self.group_stt = SttSettingsGroupWidget()
        self.group_stt.save_requested.connect(self._on_save_settings)
        layout.addWidget(self.group_stt)

        # 5. Cập nhật Ứng dụng
        self.group_update = QGroupBox(tr("settings_update_group_title", version=APP_VERSION))
        update_layout = QVBoxLayout(self.group_update)
        update_layout.setSpacing(6)

        self.lbl_update_url = QLabel(tr("settings_update_url_label"))
        self.lbl_update_url.setObjectName("FieldLabel")
        update_layout.addWidget(self.lbl_update_url)

        self.txt_update_url = QLineEdit()
        self.txt_update_url.setText(settings.update_url)
        self.txt_update_url.setPlaceholderText(get_default_update_url())
        update_layout.addWidget(self.txt_update_url)

        update_btns_row = QHBoxLayout()
        update_btns_row.setSpacing(8)
        self.btn_check_update = QPushButton(btn_text(tr("settings_btn_check_update")))
        self.btn_check_update.clicked.connect(self._on_check_update_clicked)
        update_btns_row.addWidget(self.btn_check_update)

        self.btn_reset_update_url = QPushButton(btn_text(tr("settings_btn_reset_update_url")))
        self.btn_reset_update_url.setObjectName("GhostBtn")
        self.btn_reset_update_url.clicked.connect(self._on_reset_update_url_clicked)
        update_btns_row.addWidget(self.btn_reset_update_url)
        update_btns_row.addStretch()

        update_layout.addLayout(update_btns_row)
        layout.addWidget(self.group_update)

        # 6. Đồng bộ dữ liệu giữa các máy (SQLite ⇄ PostgreSQL)
        self.group_db_sync = DatabaseSyncSettingsGroupWidget()
        layout.addWidget(self.group_db_sync)

        self.connections = HermesConnectionsSettingsWidget(settings, pool, registry)
        self.modules = ModulesToggleSettingsWidget(settings, registry, pool=pool)
        self.connections.connections_changed.connect(self.modules.reload_connections)
        self.hotkeys = HotkeySettingsGroupWidget()
        _card_layout(layout).addWidget(self.hotkeys)
        _card_layout(layout).addWidget(self.modules)
        layout.addStretch()

        i18n.language_changed.connect(self._on_language_changed_signal)

    def sync_language_combo(self, lang_code: str):
        idx = self.combo_language.findData(lang_code)
        if idx >= 0 and self.combo_language.currentIndex() != idx:
            self.combo_language.blockSignals(True)
            self.combo_language.setCurrentIndex(idx)
            self.combo_language.blockSignals(False)

    def _on_language_combo_changed(self):
        lang = self.combo_language.currentData()
        if lang and lang in SUPPORTED_LANGUAGES and lang != settings.language:
            settings.language = lang
            i18n.set_language(lang)

    def _on_language_changed_signal(self, _lang: str):
        self.retranslate_ui()

    def retranslate_ui(self):
        self.lbl_title.setText(tr("settings_title"))
        self.lbl_user_name.setText(tr("user_name_label"))
        self.lbl_language.setText(tr("settings_language_label"))
        self.lbl_character.setText(tr("settings_character_label"))
        self.btn_open_gallery.setText(btn_text(tr("settings_open_gallery_btn")))
        self.lbl_default_pomo.setText(tr("settings_pomo_mins"))
        self.lbl_ping_mins.setText(tr("settings_ping_mins"))
        self.chk_sleep_reminder.setText(tr("settings_sleep_reminder_enabled"))
        self.lbl_bedtime.setText(tr("settings_bedtime_label"))
        self.chk_exercise_reminder.setText(tr("settings_exercise_reminder_enabled"))
        self.lbl_exercise_target.setText(tr("settings_exercise_target_label"))
        self.btn_save_cfg.setText(btn_text(tr("settings_btn_save")))

        self.group_tts.retranslate_ui()
        self.group_stt.retranslate_ui()

        self.group_update.setTitle(tr("settings_update_group_title", version=APP_VERSION))
        self.lbl_update_url.setText(tr("settings_update_url_label"))
        self.btn_check_update.setText(btn_text(tr("settings_btn_check_update")))
        self.btn_reset_update_url.setText(btn_text(tr("settings_btn_reset_update_url")))
        self.group_db_sync.retranslate_ui()
        self.sync_language_combo(settings.language)
        self.connections.retranslate_ui()
        self.modules.retranslate_ui()

    def _on_save_settings(self):
        lang = self.combo_language.currentData()
        if lang and lang in SUPPORTED_LANGUAGES:
            settings.language = lang
            i18n.set_language(lang)
        settings.set_user_name(self.txt_user_name.text())
        settings.default_pomodoro_mins = self.spin_default_pomo.value()
        settings.mindful_ping_mins = self.spin_ping_mins.value()
        settings.sleep_reminder_enabled = self.chk_sleep_reminder.isChecked()
        settings.bedtime_target = self.combo_bedtime.currentText()
        settings.exercise_reminder_enabled = self.chk_exercise_reminder.isChecked()
        settings.exercise_daily_target = self.spin_exercise_target.value()
        settings.update_url = self.txt_update_url.text().strip() or get_default_update_url()

        # Lưu TTS + STT
        self.group_tts.apply_to_settings()
        self.group_stt.apply_to_settings()

        settings.save()  # không invalidate pool: lưu skin/timer/tts không được xoá lịch sử chat
        lang_display = LANGUAGE_NAMES.get(settings.language, settings.language)
        QMessageBox.information(
            self,
            tr("settings_saved_title"),
            tr("settings_saved_msg", character=settings.character_display_name, language=lang_display),
        )

    def _on_reset_update_url_clicked(self):
        default_url = get_default_update_url()
        self.txt_update_url.setText(default_url)
        settings.update_url = default_url
        settings.save()

    def _on_check_update_clicked(self):
        url = self.txt_update_url.text().strip() or get_default_update_url()
        settings.update_url = url
        settings.save()
        self.btn_check_update.setEnabled(False)
        self.btn_check_update.setText(btn_text(tr("update_checking")))
        spawn_background_task(self._async_check_update(url), name="dashboard_check_update")

    async def _async_check_update(self, url: str):
        try:
            info = await update_manager.check_for_updates(url, current_version=APP_VERSION)
            if info:
                QMessageBox.information(
                    self,
                    tr("update_found_title"),
                    tr("update_found_msg", version=info.version, changelog=info.changelog or tr("analytics_none")),
                )
            else:
                QMessageBox.information(
                    self,
                    tr("settings_saved_title"),
                    tr("update_already_latest", version=APP_VERSION),
                )
        except Exception as exc:
            QMessageBox.warning(
                self,
                tr("settings_saved_title"),
                tr("update_check_failed", error=str(exc)),
            )
        finally:
            self.btn_check_update.setEnabled(True)
            self.btn_check_update.setText(btn_text(tr("settings_btn_check_update")))
