"""Popup "🎭 Cá tính nhân vật": đặt TÊN, TÍNH CÁCH và GIỌNG NÓI riêng cho từng nhân vật.

Hành động ẩn: click nhanh 5 lần lên nhân vật trên màn hình (ghi trong tab Trợ giúp). Không nằm trong tab Cài đặt.
Chỉ cấu hình phía app — KHÔNG đổi prompt của Hermes (xem src/core/character_persona_profiles.py).
"""

from html import escape
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config import settings
from src.core.background_task_spawner import spawn_background_task
from src.core.character_persona_profiles import (
    PERSONALITIES,
    CharacterPersona,
    default_persona,
    get_personality,
    persona_for_editing,
    reset_persona,
    save_persona,
)
from src.core.i18n import get_character_skins
from src.core.offline_voice_model_catalog import get_model
from src.core.offline_voice_model_store import installed_models, resolve_model
from src.core.tts_service import tts_service
from src.ui.button_text_escape import btn_text
from src.ui.dashboard_tabs.voice_profile_dialog import VOICE_PRESETS
from src.ui.dashboard_tabs.voice_settings_group_base import field_label, labeled
from src.ui.theme import design_tokens as tk

SERVER_VOICES_VI = ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural", "vi-VN-Standard-A", "vi-VN-Standard-B"]
SERVER_VOICES_EN = ["nova", "alloy", "echo", "fable", "onyx", "shimmer", "en-US-AvaNeural", "en-US-AndrewNeural"]


def _fill_offline_combo(combo: QComboBox, language: str, current: str) -> None:
    """Giọng offline đã tải + giữ lựa chọn mặc định chưa tải (ghi chú "chưa tải") để người dùng biết cần tải gì."""
    combo.clear()
    combo.addItem("Theo cấu hình chung", "")
    for model in installed_models("tts", language):
        combo.addItem(model.title, model.id)
    if current and combo.findData(current) < 0 and get_model(current):
        combo.addItem(f"{get_model(current).title} (chưa tải)", current)
    idx = combo.findData(current)
    combo.setCurrentIndex(idx if idx >= 0 else 0)


class CharacterPersonaDialog(QDialog):
    persona_saved = Signal(str)   # skin vừa lưu

    def __init__(self, skin: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("🎭 Cá tính nhân vật")
        self.setMinimumWidth(560)
        self.setWindowFlags((self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
                            & ~Qt.WindowType.WindowContextHelpButtonHint)
        root = QVBoxLayout(self)
        root.setSpacing(10)

        hint = QLabel(f"<span style='color:{tk.TEXT_MUTED};'>Mỗi nhân vật có tên, tính cách và giọng nói riêng. "
                      f"Bộ não trò chuyện vẫn là Não AI — ở đây chỉ đổi cách nhân vật xưng tên, câu cửa miệng và giọng đọc.<br>"
                      f"💡 Mở lại bất cứ lúc nào: <b>click nhanh 5 lần</b> lên nhân vật.</span>")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.combo_skin = QComboBox()
        for key, display in get_character_skins(settings.language).items():
            self.combo_skin.addItem(display, key)
        root.addLayout(labeled(field_label("Nhân vật:"), self.combo_skin))

        self.txt_name = QLineEdit()
        self.txt_name.setMaxLength(40)
        self.txt_name.setPlaceholderText("Ví dụ: Mimi, Cú Thông Thái…")
        self.txt_name.textChanged.connect(self._update_preview)
        root.addLayout(labeled(field_label("Tên riêng:"), self.txt_name))

        self.combo_personality = QComboBox()
        for p in PERSONALITIES:
            self.combo_personality.addItem(p.title, p.key)
        self.combo_personality.currentIndexChanged.connect(self._on_personality_changed)
        root.addLayout(labeled(field_label("Tính cách:"), self.combo_personality))
        self.lbl_preview = QLabel()
        self.lbl_preview.setObjectName("Card")
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setMargin(10)
        root.addWidget(self.lbl_preview)

        # ---- Giọng nói riêng ----
        voice_card = QFrame()
        voice_card.setObjectName("Card")
        voice = QVBoxLayout(voice_card)
        voice.setContentsMargins(14, 10, 14, 10)
        self.chk_own_voice = QCheckBox("🔊 Dùng giọng nói riêng cho nhân vật này")
        self.chk_own_voice.toggled.connect(self._update_voice_enabled)
        voice.addWidget(self.chk_own_voice)
        self.voice_box = QWidget()
        vb = QVBoxLayout(self.voice_box)
        vb.setContentsMargins(0, 0, 0, 0)
        self.combo_style = QComboBox()
        self.combo_style.addItem("— Chọn nhanh phong cách giọng (điền giọng máy chủ + tốc độ) —", "")
        for key, preset in VOICE_PRESETS.items():
            self.combo_style.addItem(preset["name"], key)
        self.combo_style.currentIndexChanged.connect(self._on_style_chosen)
        vb.addWidget(self.combo_style)
        row_server = QHBoxLayout()
        self.combo_voice_vi = self._editable(SERVER_VOICES_VI)
        self.combo_voice_en = self._editable(SERVER_VOICES_EN)
        row_server.addLayout(labeled(field_label("Giọng máy chủ — Tiếng Việt:"), self.combo_voice_vi), 1)
        row_server.addLayout(labeled(field_label("Giọng máy chủ — Tiếng Anh:"), self.combo_voice_en), 1)
        vb.addLayout(row_server)
        row_offline = QHBoxLayout()
        self.combo_local_vi = QComboBox()
        self.combo_local_en = QComboBox()
        row_offline.addLayout(labeled(field_label("Giọng offline — Tiếng Việt:"), self.combo_local_vi), 1)
        row_offline.addLayout(labeled(field_label("Giọng offline — Tiếng Anh:"), self.combo_local_en), 1)
        vb.addLayout(row_offline)
        speed_row = QHBoxLayout()
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.5, 2.0)
        self.spin_speed.setSingleStep(0.05)
        speed_row.addWidget(field_label("Tốc độ đọc:"))
        speed_row.addWidget(self.spin_speed)
        speed_row.addStretch()
        vb.addLayout(speed_row)
        voice.addWidget(self.voice_box)
        root.addWidget(voice_card)

        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        buttons = QHBoxLayout()
        self.btn_test = QPushButton(btn_text("🔊 Nghe thử"))
        self.btn_test.clicked.connect(self._on_test)
        self.btn_reset = QPushButton(btn_text("↺ Về mặc định"))
        self.btn_reset.setObjectName("GhostBtn")
        self.btn_reset.clicked.connect(self._on_reset)
        btn_cancel = QPushButton(btn_text("Huỷ"))
        btn_cancel.setObjectName("GhostBtn")
        btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton(btn_text("💾 Lưu cá tính"))
        self.btn_save.setObjectName("PrimaryBtn")
        self.btn_save.clicked.connect(self._on_save)
        buttons.addWidget(self.btn_test)
        buttons.addWidget(self.btn_reset)
        buttons.addStretch()
        buttons.addWidget(btn_cancel)
        buttons.addWidget(self.btn_save)
        root.addLayout(buttons)

        skin = skin or settings.character_skin
        idx = self.combo_skin.findData(skin)
        self.combo_skin.setCurrentIndex(idx if idx >= 0 else 0)
        self._load(self.combo_skin.currentData())
        # nối sau khi dựng xong mọi ô nhập (addItem đầu tiên đã bắn currentIndexChanged)
        self.combo_skin.currentIndexChanged.connect(lambda _i: self._load(self.combo_skin.currentData()))

    @staticmethod
    def _editable(items) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(items)
        return combo

    # ---------- nạp / đọc form ----------
    def _load(self, skin: str, persona: Optional[CharacterPersona] = None) -> None:
        persona = persona or persona_for_editing(skin)
        self.txt_name.setText(persona.name)
        idx = self.combo_personality.findData(persona.personality)
        self.combo_personality.blockSignals(True)
        self.combo_personality.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_personality.blockSignals(False)
        self.chk_own_voice.setChecked(persona.use_own_voice)
        self.combo_voice_vi.setCurrentText(persona.voice_vi)
        self.combo_voice_en.setCurrentText(persona.voice_en)
        self.spin_speed.setValue(persona.speed)
        _fill_offline_combo(self.combo_local_vi, "vi", persona.local_voice_vi)
        _fill_offline_combo(self.combo_local_en, "en", persona.local_voice_en)
        self._update_voice_enabled()
        self._update_preview()

    def current_persona(self) -> CharacterPersona:
        skin = self.combo_skin.currentData()
        return CharacterPersona(
            skin=skin, name=self.txt_name.text().strip() or default_persona(skin).name,
            personality=self.combo_personality.currentData(), use_own_voice=self.chk_own_voice.isChecked(),
            voice_vi=self.combo_voice_vi.currentText().strip(), voice_en=self.combo_voice_en.currentText().strip(),
            local_voice_vi=self.combo_local_vi.currentData() or "", local_voice_en=self.combo_local_en.currentData() or "",
            speed=round(self.spin_speed.value(), 2),
        )

    # ---------- phản hồi UI ----------
    def _update_voice_enabled(self, *_args) -> None:
        self.voice_box.setEnabled(self.chk_own_voice.isChecked())

    def _on_personality_changed(self, *_args) -> None:
        self.spin_speed.setValue(get_personality(self.combo_personality.currentData()).suggested_speed)
        self._update_preview()

    def _update_preview(self, *_args) -> None:
        persona = self.current_persona()
        profile = persona.personality_profile
        lines = "".join(f"<li>{escape(line)}</li>" for line in persona.catchphrases())
        self.lbl_preview.setText(
            f"<b>{escape(profile.title)}</b> — {escape(profile.description)}<br>"
            f"<span style='color:{tk.PRIMARY_SOFT};'>“{escape(persona.greeting())}”</span>"
            f"<ul style='margin:2px 0;'>{lines}</ul>")

    def _on_style_chosen(self, *_args) -> None:
        preset = VOICE_PRESETS.get(self.combo_style.currentData() or "")
        if preset:
            self.combo_voice_vi.setCurrentText(preset["voice_vi"])
            self.combo_voice_en.setCurrentText(preset["voice_en"])
            self.spin_speed.setValue(preset["speed"])
            self.lbl_status.setText(f"<span style='color:{tk.TERTIARY};'>Đã điền phong cách: {escape(preset['name'])}</span>")

    # ---------- hành động ----------
    def _on_test(self) -> None:
        persona = self.current_persona()
        text = persona.greeting()
        self.lbl_status.setText(f"<span style='color:{tk.TEXT_MUTED};'>Đang đọc thử…</span>")
        if tts_service.get_effective_mode() == "embedded":
            model = resolve_model("tts", persona.local_voice_vi if persona.use_own_voice else "", "vi")
            coro = tts_service.test_offline_voice(model.id if model else "", text, persona.speed)
        else:
            coro = tts_service.test_connection(
                server_url=settings.tts_server_url, voice=persona.voice_vi or settings.tts_voice_vi, test_text=text,
                api_key=settings.tts_api_key, model=settings.tts_model, speed=persona.speed)

        async def _run():
            ok, msg = await coro
            color = tk.TERTIARY if ok else tk.ERROR
            self.lbl_status.setText(f"<span style='color:{color};'>{'✅' if ok else '❌'} {escape(msg)}</span>")

        spawn_background_task(_run(), "persona-voice-test")

    def _on_reset(self) -> None:
        skin = self.combo_skin.currentData()
        reset_persona(skin)
        self._load(skin, default_persona(skin))
        self.lbl_status.setText(f"<span style='color:{tk.TERTIARY};'>Đã về mặc định (tên & giọng gốc của app).</span>")
        self.persona_saved.emit(skin)

    def _on_save(self) -> None:
        persona = self.current_persona()
        save_persona(persona)
        self.persona_saved.emit(persona.skin)
        self.accept()
