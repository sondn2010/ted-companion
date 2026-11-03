"""Chọn giọng (speaker) của VieNeu-TTS trong Cài đặt → Giọng nói.

Chỉ hiện khi mô hình tiếng Việt đang chọn là VieNeu và đã tải xong. Danh sách giọng đọc từ cache tĩnh ghi lúc cài
(`list_vieneu_voices`, không cần sidecar) → 3 trạng thái: đang tải / lỗi (có nút Thử lại) / chọn giọng.
Lựa chọn lưu theo TỪNG model vào `settings.vieneu_voices[model_id]` khi `commit()` ("" = giọng mặc định của model).
"""

from html import escape
from typing import Awaitable, Callable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src.config import settings
from src.core.background_task_spawner import spawn_background_task
from src.core.offline_voice_model_catalog import get_model
from src.core.offline_voice_model_store import is_model_installed
from src.core.vieneu_sidecar_tts_engine import VieneuVoice, list_vieneu_voices
from src.ui.button_text_escape import btn_text
from src.ui.dashboard_tabs.voice_settings_group_base import field_label
from src.ui.theme import design_tokens as tk

VoiceProvider = Callable[[str], Awaitable[list[VieneuVoice]]]


class VieneuVoicePickerWidget(QWidget):
    test_requested = Signal()   # bấm "Nghe thử": nhóm cha chạy kiểm tra qua đường TTS offline (engine VieNeu)

    def __init__(self, provider: VoiceProvider = list_vieneu_voices, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._provider = provider
        self._model_id = ""
        self._loaded_model_id = ""   # model đã nạp xong danh sách (tránh nạp lại, tránh khởi động sidecar vô ích)
        self._generation = 0         # bỏ kết quả của lượt nạp cũ khi người dùng đổi model giữa chừng
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.lbl_title = field_label("Giọng VieNeu (người đọc):")
        layout.addWidget(self.lbl_title)
        row = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setObjectName("VieneuVoiceCombo")
        row.addWidget(self.combo, stretch=1)
        self.btn_retry = QPushButton(btn_text("🔄 Thử lại"))
        self.btn_retry.setObjectName("GhostBtn")
        self.btn_retry.clicked.connect(self.reload)
        row.addWidget(self.btn_retry)
        self.btn_test = QPushButton(btn_text("🔊 Nghe thử"))
        self.btn_test.setObjectName("GhostBtn")
        self.btn_test.clicked.connect(self._on_test_clicked)
        row.addWidget(self.btn_test)
        layout.addLayout(row)
        self.lbl_state = QLabel()
        self.lbl_state.setWordWrap(True)
        layout.addWidget(self.lbl_state)
        self._show_state("idle")
        self.setVisible(False)

    # ---------- API cho nhóm cha ----------
    def set_model(self, model_id: str) -> None:
        """Gọi mỗi khi model tiếng Việt đang chọn thay đổi. Không phải VieNeu / chưa tải → ẩn."""
        model = get_model(model_id) if model_id else None
        usable = bool(model and model.engine == "vieneu" and is_model_installed(model))
        new_id = model_id if usable else ""
        if new_id != self._model_id:
            self._generation += 1   # huỷ lượt nạp của model cũ đang chờ (kể cả khi widget đang ẩn)
            self._loaded_model_id = ""
            if self._state == "loading":
                self._show_state("idle")   # showEvent/reload mới được phép nạp lại cho model mới
        self._model_id = new_id
        self.setVisible(usable)
        if not usable:
            return
        if self.isVisible() and self._loaded_model_id != self._model_id:
            self.reload()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._model_id and self._loaded_model_id != self._model_id and self._state != "loading":
            self.reload()

    def reload(self) -> None:
        spawn_background_task(self.load(), "load-vieneu-voices")

    async def load(self) -> None:
        """Nạp danh sách giọng của model hiện tại; lỗi hiển thị trên widget (không ném ra ngoài)."""
        model_id = self._model_id
        if not model_id:
            return
        self._generation += 1
        generation = self._generation
        self._show_state("loading")
        try:
            voices = await self._provider(model_id)
        except Exception as exc:   # sidecar không khởi động / chưa cài / mạng nội bộ lỗi
            if generation == self._generation:
                self._show_state("error", str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__)
            return
        if generation != self._generation or model_id != self._model_id:
            return   # đổi model giữa chừng: bỏ kết quả của model cũ
        self._fill(voices, model_id)

    def commit(self) -> None:
        """Ghi giọng đang chọn vào settings (không đụng khi chưa nạp được danh sách — giữ giá trị cũ)."""
        if self._model_id and self._loaded_model_id == self._model_id:
            settings.vieneu_voices[self._model_id] = self.combo.currentData() or ""

    # ---------- nội bộ ----------
    def _fill(self, voices: list[VieneuVoice], model_id: str) -> None:
        saved = settings.vieneu_voices.get(model_id, "")
        self.combo.clear()
        default = next((v for v in voices if v.is_default), None)
        self.combo.addItem(f"Mặc định ({default.name})" if default else "Mặc định", "")
        for voice in voices:
            self.combo.addItem(voice.name, voice.id)
        idx = self.combo.findData(saved)
        self.combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._loaded_model_id = model_id
        self._show_state("ready")

    def _show_state(self, state: str, detail: str = "") -> None:
        self._state = state
        self.combo.setEnabled(state == "ready")
        self.btn_test.setEnabled(state == "ready")
        self.btn_retry.setVisible(state == "error")
        if state == "loading":
            self.combo.clear()
            self.combo.addItem("Đang tải danh sách giọng…", "")
            self.lbl_state.setText(f"<span style='color:{tk.TEXT_MUTED};'>Lần đầu cần khởi động bộ đọc (~5 giây).</span>")
        elif state == "error":
            self.combo.clear()
            self.combo.addItem("Không tải được danh sách giọng", "")
            self.lbl_state.setText(f"<span style='color:{tk.ERROR};'>❌ {escape(detail)}</span>")
        else:
            self.lbl_state.setText("")

    def _on_test_clicked(self) -> None:
        self.commit()   # nghe thử dùng settings.vieneu_voices → phải ghi trước
        self.test_requested.emit()
