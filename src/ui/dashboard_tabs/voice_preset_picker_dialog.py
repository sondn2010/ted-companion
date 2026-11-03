"""Popup chọn cấu hình mẫu TTS/STT có ô tìm kiếm (gõ không dấu cũng được).

Chọn preset → xem trước các giá trị sẽ điền + cảnh báo (cần tải model / cần API key) → "Điền vào cấu hình".
Popup KHÔNG tự lưu: phát `preset_chosen(VoiceConfigPreset)` để group widget điền vào các ô input.
"""

from html import escape
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.offline_voice_model_catalog import get_model
from src.core.offline_voice_model_store import is_model_installed
from src.core.voice_config_presets import VoiceConfigPreset, search_presets
from src.ui.button_text_escape import btn_text
from src.ui.theme import design_tokens as tk

PRESET_ROLE = Qt.ItemDataRole.UserRole

# Nhãn thân thiện cho từng khoá settings hiển thị trong phần xem trước
FIELD_LABELS = {
    "tts_mode": "Chế độ", "stt_mode": "Chế độ",
    "tts_server_url": "Địa chỉ máy chủ", "stt_server_url": "Địa chỉ máy chủ",
    "tts_api_key": "API key", "stt_api_key": "API key",
    "tts_model": "Model", "stt_model": "Model",
    "tts_voice_vi": "Giọng tiếng Việt", "tts_voice_en": "Giọng tiếng Anh",
    "tts_local_voice_vi": "Giọng tiếng Việt", "tts_local_voice_en": "Giọng tiếng Anh",
    "stt_local_model": "Mô hình", "tts_speed": "Tốc độ đọc", "stt_language": "Ngôn ngữ nói",
}
MODE_LABELS = {"embedded": "Trên máy (offline)", "server": "Máy chủ", "auto": "Tự động"}


def missing_models(preset: VoiceConfigPreset) -> list:
    """Các model offline preset cần nhưng chưa tải."""
    models = [get_model(mid) for mid in dict.fromkeys(preset.requires_models) if mid]
    return [m for m in models if m is not None and not is_model_installed(m)]


def _display_value(key: str, value) -> str:
    if key.endswith("_mode"):
        return MODE_LABELS.get(value, value)
    if key.endswith("api_key"):
        return "•••• (mặc định của máy chủ)" if value else "(không cần)"
    if key in ("tts_local_voice_vi", "tts_local_voice_en", "stt_local_model"):
        model = get_model(value)
        return model.title if model else value
    if key == "tts_speed":
        return f"{value}x"
    if key == "stt_language":
        return {"vi": "Tiếng Việt", "en": "Tiếng Anh"}.get(value, value)
    return str(value)


class VoicePresetPickerDialog(QDialog):
    preset_chosen = Signal(object)   # VoiceConfigPreset

    def __init__(self, kind: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle("✨ Chọn cấu hình giọng đọc mẫu" if kind == "tts" else "✨ Chọn cấu hình nhận giọng nói mẫu")
        self.setMinimumSize(620, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        intro = QLabel("Chọn một mẫu phù hợp — app sẽ <b>điền sẵn mọi ô cấu hình</b>, bạn chỉ cần bấm Nghe thử rồi Lưu.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎 Tìm: nữ, nam, chậm, offline, tiếng Anh, máy yếu, openai…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refill)
        layout.addWidget(self.search)

        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMinimumWidth(270)
        self.list.currentItemChanged.connect(self._on_current_changed)
        self.list.itemDoubleClicked.connect(lambda _item: self._apply())
        body.addWidget(self.list, stretch=5)

        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.TextFormat.RichText)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.detail.setObjectName("Card")
        self.detail.setMargin(12)
        body.addWidget(self.detail, stretch=6)
        layout.addLayout(body, stretch=1)

        self.lbl_count = QLabel()
        self.lbl_count.setObjectName("MutedLabel")
        buttons = QHBoxLayout()
        buttons.addWidget(self.lbl_count)
        buttons.addStretch()
        btn_close = QPushButton(btn_text("Đóng"))
        btn_close.setObjectName("GhostBtn")
        btn_close.clicked.connect(self.reject)
        self.btn_apply = QPushButton(btn_text("✅ Điền vào cấu hình"))
        self.btn_apply.setObjectName("PrimaryBtn")
        self.btn_apply.clicked.connect(self._apply)
        buttons.addWidget(btn_close)
        buttons.addWidget(self.btn_apply)
        layout.addLayout(buttons)

        self._refill()
        self.search.setFocus()

    # ---------- danh sách ----------
    def _refill(self) -> None:
        presets = search_presets(self.kind, self.search.text())
        self.list.blockSignals(True)
        self.list.clear()
        group = None
        first_item = None
        for preset in presets:
            if preset.group != group:
                group = preset.group
                header = QListWidgetItem(group)
                header.setFlags(Qt.ItemFlag.NoItemFlags)   # tiêu đề nhóm: không chọn được
                font = header.font()
                font.setBold(True)
                header.setFont(font)
                self.list.addItem(header)
            label = ("⭐ " if preset.recommended else "   ") + preset.title
            item = QListWidgetItem(label)
            item.setData(PRESET_ROLE, preset.id)
            self.list.addItem(item)
            if first_item is None or (preset.recommended and not first_item.text().startswith("⭐")):
                first_item = item
        self.list.blockSignals(False)
        self.lbl_count.setText(f"{len(presets)} mẫu")
        self._presets = {p.id: p for p in presets}
        if first_item is not None:
            self.list.setCurrentItem(first_item)
        else:
            self.detail.setText(f"<span style='color:{tk.TEXT_MUTED};'>Không tìm thấy mẫu nào. Thử từ khoá khác nhé.</span>")
        self.btn_apply.setEnabled(first_item is not None)

    def selected_preset(self) -> Optional[VoiceConfigPreset]:
        item = self.list.currentItem()
        return self._presets.get(item.data(PRESET_ROLE)) if item is not None else None

    def select_preset(self, preset_id: str) -> bool:
        for row in range(self.list.count()):
            if self.list.item(row).data(PRESET_ROLE) == preset_id:
                self.list.setCurrentRow(row)
                return True
        return False

    # ---------- xem trước ----------
    def _on_current_changed(self, current, _previous) -> None:
        preset = self.selected_preset()
        self.btn_apply.setEnabled(preset is not None)
        if preset is None:
            return
        rows = "".join(
            f"<tr><td style='color:{tk.TEXT_MUTED}; padding-right:10px;'>{escape(FIELD_LABELS.get(k, k))}</td>"
            f"<td>{escape(_display_value(k, v))}</td></tr>"
            for k, v in preset.values.items()
        )
        notes = []
        missing = missing_models(preset)
        if missing:
            total = sum(m.size_mb for m in missing)
            names = ", ".join(escape(m.title) for m in missing)
            notes.append(f"<p style='color:{tk.WARNING};'>⬇️ Cần tải thêm: {names} (~{total} MB). "
                         f"App sẽ hỏi tải ngay sau khi điền.</p>")
        elif preset.requires_models:
            notes.append(f"<p style='color:{tk.TERTIARY};'>✅ Đã có sẵn mô hình trên máy.</p>")
        if preset.needs_api_key:
            notes.append(f"<p style='color:{tk.WARNING};'>🔑 Cần API key của dịch vụ — điền vào ô API Key sau khi chọn.</p>")
        self.detail.setText(
            f"<p style='font-size:15px;'><b>{escape(preset.title)}</b></p>"
            f"<p style='color:{tk.TEXT_MUTED};'>{escape(preset.group)}</p>"
            f"<p>{escape(preset.description)}</p>"
            f"<p><b>Sẽ điền:</b></p><table>{rows}</table>{''.join(notes)}"
        )

    def _apply(self) -> None:
        preset = self.selected_preset()
        if preset is None:
            return
        self.preset_chosen.emit(preset)
        self.accept()
