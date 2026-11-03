"""
Dialog chọn và tuỳ biến mẫu giọng nói (Voice Profile Dialog).
Hỗ trợ prefill sẵn các phong cách giọng nói chuẩn theo độ tuổi & giới tính:
- Nam trầm ấm, già dặn (~40-50 tuổi)
- Nữ trầm ấm, trưởng thành (~35-45 tuổi)
- Nam trẻ trung, năng động (~18-22 tuổi)
- Nữ trẻ trung, ngọt ngào (~18-20 tuổi)
- Giọng công sở chuẩn mực (~30 tuổi)
- Giọng chánh niệm / thư giãn Deep Work
"""

from typing import Dict, Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config import settings
from src.core.background_task_spawner import spawn_background_task
from src.core.i18n import tr
from src.ui.button_text_escape import btn_text
from src.core.tts_service import tts_service
from src.ui.theme import design_tokens as tk


# Bảng presets phong phú phân loại theo độ tuổi, giới tính và ngữ điệu
VOICE_PRESETS: Dict[str, Dict[str, Any]] = {
    "male_mature_warm_40s": {
        "name": "👨 Nam Trầm ấm, Già dặn (~40-50 tuổi)",
        "tag": "Trưởng thành • Điềm đạm • Vững chãi",
        "description": "Giọng nam trung niên đĩnh đạc, âm sắc trầm dày, nhịp điệu chậm rãi (0.85x). Phù hợp làm cố vấn, định hướng và tạo sự tin tưởng tuyệt đối.",
        "model": "tts-1",
        "voice_vi": "vi-VN-NamMinhNeural",
        "voice_en": "onyx",
        "speed": 0.85,
    },
    "female_mature_warm_40s": {
        "name": "👩 Nữ Trầm ấm, Trưởng thành (~35-45 tuổi)",
        "tag": "Trầm ấm • Thấu hiểu • Điềm tĩnh",
        "description": "Giọng nữ chín chắn, ấm áp, nhịp điệu từ tốn (0.9x). Rất phù hợp khi nhắc nhở công việc nhẹ nhàng, lắng nghe tâm sự và giảm stress.",
        "model": "tts-1",
        "voice_vi": "vi-VN-HoaiMyNeural",
        "voice_en": "shimmer",
        "speed": 0.9,
    },
    "male_young_energetic_18s": {
        "name": "👦 Nam Trẻ trung, Năng động (~18-22 tuổi)",
        "tag": "Năng lượng • Tươi sáng • Hoạt bát",
        "description": "Giọng nam thanh niên tươi vui, hào hứng, nhịp đọc nhanh (1.1x). Tiếp thêm động lực mạnh mẽ để khởi động ngày mới và bứt phá mục tiêu.",
        "model": "tts-1",
        "voice_vi": "vi-VN-Standard-B",
        "voice_en": "fable",
        "speed": 1.1,
    },
    "female_young_sweet_18s": {
        "name": "👧 Nữ Trẻ trung, Ngọt ngào (~18-20 tuổi)",
        "tag": "Trong trẻo • Ngọt ngào • Động viên",
        "description": "Giọng nữ trong trẻo, dễ thương, tươi vui, tốc độ đọc 1.1x. Mang lại cảm giác gần gũi như một người bạn thân cổ vũ học tập và làm việc.",
        "model": "tts-1",
        "voice_vi": "vi-VN-Standard-A",
        "voice_en": "nova",
        "speed": 1.1,
    },
    "male_office_neutral_30s": {
        "name": "👔 Nam Chuẩn mực Công sở (~28-32 tuổi)",
        "tag": "Chuyên nghiệp • Rõ ràng • Trung tính",
        "description": "Giọng nam công sở chuẩn mực, tốc độ 1.0x chuẩn, ngắt nghỉ câu rõ chữ. Lý tưởng cho phiên làm việc Deep Work cần sự tập trung cao độ.",
        "model": "tts-1",
        "voice_vi": "vi-VN-Standard-B",
        "voice_en": "echo",
        "speed": 1.0,
    },
    "female_office_assistant_30s": {
        "name": "👩‍💼 Nữ Trợ lý Tận tâm (~28-32 tuổi)",
        "tag": "Chu đáo • Chuyên nghiệp • Thanh lịch",
        "description": "Giọng nữ trợ lý thông minh, truyền cảm, nhịp đọc 1.0x. Thích hợp thông báo lịch hẹn, tóm tắt công việc và báo cáo cuối ngày.",
        "model": "tts-1",
        "voice_vi": "vi-VN-Standard-A",
        "voice_en": "alloy",
        "speed": 1.0,
    },
    "mindful_meditation_deepwork": {
        "name": "🧘 Giọng Chánh niệm & Thư giãn (Deep Work)",
        "tag": "Êm dịu • Thiền định • Thư thái",
        "description": "Giọng đọc chậm rãi (0.8x), ngân vang dịu nhẹ. Tuyệt vời khi dùng cho Mindful Ping định kỳ, nhắc hít thở và giải tỏa căng thẳng mắt.",
        "model": "tts-1",
        "voice_vi": "vi-VN-Standard-A",
        "voice_en": "alloy",
        "speed": 0.8,
    },
}


class VoiceProfileDialog(QDialog):
    """Cửa sổ Popup chọn mẫu giọng nói theo phong cách và tự động điền tham số."""

    profile_applied = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("🎙️ Chọn Mẫu Giọng Nói & Tinh Chỉnh Âm Sắc")
        self.setMinimumSize(560, 640)
        self.resize(580, 680)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._init_ui()
        self._load_current_or_default()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # 1. Header tiêu đề
        lbl_title = QLabel("🎙️ Cấu hình Giọng nói Chuyên sâu")
        lbl_title.setObjectName("TitleLabel")
        main_layout.addWidget(lbl_title)

        lbl_subtitle = QLabel(
            "Chọn mẫu giọng nói chuẩn theo giới tính & độ tuổi hoặc tùy chỉnh trực tiếp Voice ID, tốc độ đọc theo nhu cầu."
        )
        lbl_subtitle.setWordWrap(True)
        lbl_subtitle.setObjectName("HintLabel")
        main_layout.addWidget(lbl_subtitle)

        # 2. Hộp chọn Preset phong cách
        grp_preset = QGroupBox("1. Chọn Mẫu Giọng nói Thiết kế sẵn (Presets)")
        grp_preset_layout = QVBoxLayout(grp_preset)
        grp_preset_layout.setSpacing(8)

        self.combo_presets = QComboBox()
        for key, p in VOICE_PRESETS.items():
            self.combo_presets.addItem(p["name"], key)
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        grp_preset_layout.addWidget(self.combo_presets)

        # Khung mô tả preset được chọn
        self.desc_frame = QFrame()
        self.desc_frame.setObjectName("InfoPanel")
        desc_layout = QVBoxLayout(self.desc_frame)
        desc_layout.setContentsMargins(10, 8, 10, 8)
        desc_layout.setSpacing(4)

        self.lbl_tag = QLabel()
        self.lbl_tag.setObjectName("Chip")
        desc_layout.addWidget(self.lbl_tag, alignment=Qt.AlignmentFlag.AlignLeft)

        self.lbl_desc = QLabel()
        self.lbl_desc.setWordWrap(True)
        desc_layout.addWidget(self.lbl_desc)

        grp_preset_layout.addWidget(self.desc_frame)
        main_layout.addWidget(grp_preset)

        # 3. Hộp thông số chi tiết (Tự động điền - có thể tinh chỉnh)
        grp_params = QGroupBox("2. Tham số Chi tiết (Được tự động điền theo Mẫu)")
        params_layout = QVBoxLayout(grp_params)
        params_layout.setSpacing(10)

        # Model TTS
        row_model = QHBoxLayout()
        lbl_m = QLabel("Model TTS:")
        lbl_m.setFixedWidth(130)
        lbl_m.setObjectName("FieldLabel")
        row_model.addWidget(lbl_m)
        self.txt_model = QLineEdit()
        self.txt_model.setPlaceholderText("tts-1 hoặc kokoro")
        row_model.addWidget(self.txt_model)
        params_layout.addLayout(row_model)

        # Voice Tiếng Việt
        row_vi = QHBoxLayout()
        lbl_v_vi = QLabel("Giọng Tiếng Việt:")
        lbl_v_vi.setFixedWidth(130)
        lbl_v_vi.setObjectName("FieldLabel")
        row_vi.addWidget(lbl_v_vi)
        self.combo_voice_vi = QComboBox()
        self.combo_voice_vi.setEditable(True)
        self.combo_voice_vi.addItems([
            "vi-VN-Standard-A",
            "vi-VN-Standard-B",
            "vi-VN-HoaiMyNeural",
            "vi-VN-NamMinhNeural",
            "vi_female",
            "vi_male_young",
            "vi_male_deep",
        ])
        row_vi.addWidget(self.combo_voice_vi)
        params_layout.addLayout(row_vi)

        # Voice Tiếng Anh
        row_en = QHBoxLayout()
        lbl_v_en = QLabel("Giọng Tiếng Anh:")
        lbl_v_en.setFixedWidth(130)
        lbl_v_en.setObjectName("FieldLabel")
        row_en.addWidget(lbl_v_en)
        self.combo_voice_en = QComboBox()
        self.combo_voice_en.setEditable(True)
        self.combo_voice_en.addItems([
            "alloy",
            "echo",
            "fable",
            "onyx",
            "nova",
            "shimmer",
            "en-US-Standard-C",
            "af_heart",
            "af_nicole",
            "am_michael",
            "am_adam",
        ])
        row_en.addWidget(self.combo_voice_en)
        params_layout.addLayout(row_en)

        # Tốc độ đọc
        row_spd = QHBoxLayout()
        lbl_spd = QLabel("Tốc độ đọc (Speed):")
        lbl_spd.setFixedWidth(130)
        lbl_spd.setObjectName("FieldLabel")
        row_spd.addWidget(lbl_spd)
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.5, 2.0)
        self.spin_speed.setSingleStep(0.05)
        row_spd.addWidget(self.spin_speed)

        lbl_spd_hint = QLabel("(Chậm 0.85x = Già dặn, trầm; Nhanh 1.1x = Trẻ trung)")
        lbl_spd_hint.setObjectName("HintLabel")
        row_spd.addWidget(lbl_spd_hint)
        row_spd.addStretch()
        params_layout.addLayout(row_spd)

        main_layout.addWidget(grp_params)

        # 4. Hộp Nghe thử giọng nói
        grp_test = QGroupBox("3. Nghe Thử Trực Tiếp (Live Audition)")
        test_layout = QVBoxLayout(grp_test)
        test_layout.setSpacing(8)

        test_btns_row = QHBoxLayout()
        test_btns_row.setSpacing(10)
        self.btn_test_vi = QPushButton("🔊 Thử Tiếng Việt")
        self.btn_test_vi.clicked.connect(self._on_test_vi_clicked)
        test_btns_row.addWidget(self.btn_test_vi)

        self.btn_test_en = QPushButton("🔊 Thử Tiếng Anh")
        self.btn_test_en.clicked.connect(self._on_test_en_clicked)
        test_btns_row.addWidget(self.btn_test_en)
        test_btns_row.addStretch()
        test_layout.addLayout(test_btns_row)

        self.lbl_test_status = QLabel()
        self.lbl_test_status.setObjectName("HintLabel")
        test_layout.addWidget(self.lbl_test_status)

        main_layout.addWidget(grp_test)

        # 5. Thanh nút Lưu & Áp dụng
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)

        self.btn_apply = QPushButton("💾 Áp Dụng Mẫu Này")
        self.btn_apply.setObjectName("PrimaryBtn")
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        actions_row.addWidget(self.btn_apply)

        self.btn_close = QPushButton("Đóng")
        self.btn_close.setObjectName("GhostBtn")
        self.btn_close.clicked.connect(self.reject)
        actions_row.addWidget(self.btn_close)

        actions_row.addStretch()
        main_layout.addLayout(actions_row)

    def _load_current_or_default(self):
        # Mặc định kích hoạt preset đầu tiên
        self._on_preset_changed(0)

    def _on_preset_changed(self, index: int):
        key = self.combo_presets.itemData(index)
        preset = VOICE_PRESETS.get(key)
        if not preset:
            return

        self.lbl_tag.setText(preset["tag"])
        self.lbl_desc.setText(preset["description"])

        # Tự động prefill các trường
        self.txt_model.setText(preset["model"])
        self.combo_voice_vi.setCurrentText(preset["voice_vi"])
        self.combo_voice_en.setCurrentText(preset["voice_en"])
        self.spin_speed.setValue(preset["speed"])
        self.lbl_test_status.setText("")

    def _on_test_vi_clicked(self):
        text = "Xin chào bạn, tôi là Ted luôn sẵn sàng đồng hành cùng bạn tập trung deep work!"
        self._run_test(voice=self.combo_voice_vi.currentText().strip(), text=text)

    def _on_test_en_clicked(self):
        text = "Hello there, I am Ted, your mindful companion ready for a deep work session!"
        self._run_test(voice=self.combo_voice_en.currentText().strip(), text=text)

    def _run_test(self, voice: str, text: str):
        url = getattr(settings, "tts_server_url", "http://127.0.0.1:8880/v1")
        key = getattr(settings, "tts_api_key", "")
        model = self.txt_model.text().strip() or "tts-1"
        speed = round(self.spin_speed.value(), 2)

        self.lbl_test_status.setText("⏳ Đang kết nối server TTS...")

        async def _test():
            ok, msg = await tts_service.test_connection(
                server_url=url,
                voice=voice,
                test_text=text,
                api_key=key,
                model=model,
                speed=speed,
            )
            if ok:
                self.lbl_test_status.setText(f"<span style='color:{tk.TERTIARY};'>✅ Phát giọng nói thành công!</span>")
            else:
                self.lbl_test_status.setText(f"<span style='color:{tk.ERROR};'>❌ Lỗi TTS: {msg}</span>")

        spawn_background_task(_test(), "test-voice-profile-dialog")

    def _on_apply_clicked(self):
        data = {
            "model": self.txt_model.text().strip() or "tts-1",
            "voice_vi": self.combo_voice_vi.currentText().strip() or "vi-VN-Standard-A",
            "voice_en": self.combo_voice_en.currentText().strip() or "en-US-Standard-C",
            "speed": round(self.spin_speed.value(), 2),
        }
        self.profile_applied.emit(data)
        self.accept()
