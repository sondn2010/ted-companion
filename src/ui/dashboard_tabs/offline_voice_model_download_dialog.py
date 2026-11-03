"""Popup tải mô hình giọng nói OFFLINE (TTS: giọng Piper · STT: whisper.cpp) cho người dùng phổ thông.

Luồng 3 bước hiển thị ngay trên popup:
  ① Chọn mô hình (có dung lượng, chất lượng, ⭐ khuyên dùng, trạng thái đã tải)  →
  ② Tải về (thanh tiến trình, huỷ được; lần đầu tải kèm bộ chạy nhỏ)              →
  ③ Hướng dẫn + app TỰ ĐIỀN cấu hình (phát `models_ready`), nút Nghe thử / Chạy thử.
"""

import asyncio
from html import escape
from typing import Iterable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core.background_task_spawner import spawn_background_task
from src.core.offline_voice_model_catalog import OfflineVoiceModel, models_for, runtime_for
from src.core.offline_voice_model_store import (
    DownloadCancelled,
    delete_model,
    download_model,
    find_runtime_executable,
    is_model_installed,
    voice_models_root,
)
from src.ui.button_text_escape import btn_text
from src.ui.dashboard_tabs.voice_download_progress_text import format_download_progress
from src.ui.theme import design_tokens as tk

# Ghi chú chung cho cả Turbo lẫn Nano (chất lượng từng bản đã nằm trong mô tả của catalog)
VIENEU_DOWNLOAD_NOTE = "Tải lần đầu ~15–20 phút (Python + thư viện + model), cần ~1–2 GB ổ đĩa"
LANG_BADGE = {"vi": "🇻🇳 Tiếng Việt", "en": "🇬🇧 Tiếng Anh", "multi": "🌐 Đa ngôn ngữ"}


def _stars(n: int) -> str:
    return "★" * n + "☆" * (5 - n)


class _ModelRow(QFrame):
    """1 thẻ mô hình: checkbox chọn tải + thông tin + nút xoá khi đã tải."""

    def __init__(self, model: OfflineVoiceModel, on_delete, parent=None):
        super().__init__(parent)
        self.model = model
        self.setObjectName("Card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        self.check = QCheckBox()
        layout.addWidget(self.check, alignment=Qt.AlignmentFlag.AlignTop)
        info = QLabel()
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)
        badge = f" <span style='color:{tk.WARNING};'>⭐ Khuyên dùng</span>" if model.recommended else ""
        info.setText(
            f"<b>{escape(model.title)}</b>{badge}<br>"
            f"<span style='color:{tk.TEXT_MUTED};'>{LANG_BADGE.get(model.language, '')} · {model.size_mb} MB · "
            f"Chất lượng {_stars(model.quality)} · {escape(model.speed_note)}</span><br>{escape(model.description)}"
            + (f"<br><span style='color:{tk.WARNING};'>ℹ️ {escape(VIENEU_DOWNLOAD_NOTE)}</span>"
               if model.engine == "vieneu" else "")
        )
        info.mousePressEvent = lambda _e: self.check.toggle() if self.check.isEnabled() else None
        layout.addWidget(info, stretch=1)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.btn_delete = QPushButton(btn_text("🗑 Xoá"))
        self.btn_delete.setObjectName("GhostBtn")
        self.btn_delete.setToolTip("Xoá mô hình khỏi máy để giải phóng dung lượng")
        self.btn_delete.clicked.connect(lambda: on_delete(self))
        layout.addWidget(self.btn_delete)
        self.refresh()

    def refresh(self) -> None:
        installed = is_model_installed(self.model)
        self.status.setText(f"<span style='color:{tk.TERTIARY};'>✅ Đã tải</span>" if installed else "")
        self.btn_delete.setVisible(installed)
        self.check.setEnabled(not installed)
        if installed:
            self.check.setChecked(False)


class OfflineVoiceModelDownloadDialog(QDialog):
    models_ready = Signal(list)   # list[str] id các model vừa tải xong (để group widget tự điền cấu hình)
    test_requested = Signal()     # người dùng bấm Nghe thử / Chạy thử ở bước ③

    def __init__(self, kind: str, preselect_ids: Iterable[str] = (), parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.kind = kind
        self._cancel: Optional[asyncio.Event] = None
        self._downloading = False
        self._deleting = False   # đang gỡ VieNeu trên luồng nền: khoá nút tải/xoá, hiện trạng thái bận
        noun = "giọng đọc" if kind == "tts" else "mô hình nhận giọng nói"
        self.setWindowTitle(f"⬇️ Tải {noun} offline")
        self.setMinimumSize(620, 600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        steps = QLabel(
            f"<b>① Chọn {noun}</b> &nbsp;→&nbsp; <b>② Tải về</b> &nbsp;→&nbsp; <b>③ App tự điền cấu hình</b><br>"
            f"<span style='color:{tk.TEXT_MUTED};'>Mô hình lưu ngay trên máy bạn ({escape(str(voice_models_root()))}), "
            f"sau khi tải không cần internet. Bộ cài Ted không kèm sẵn để nhẹ hơn.</span>"
        )
        steps.setWordWrap(True)
        layout.addWidget(steps)

        self.lbl_runtime = QLabel()
        self.lbl_runtime.setWordWrap(True)
        layout.addWidget(self.lbl_runtime)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        holder = QWidget()
        rows_layout = QVBoxLayout(holder)
        rows_layout.setSpacing(6)
        preselect = set(preselect_ids)   # VieNeu (~1,4 GB, ~20 phút) không tự tích sẵn: người dùng chủ động chọn
        self.rows: list[_ModelRow] = []
        for model in models_for(kind):
            row = _ModelRow(model, self._on_delete_row)
            if not is_model_installed(model) and (model.id in preselect or (not preselect and model.recommended and model.engine != "vieneu")):
                row.check.setChecked(True)
            row.check.toggled.connect(self._update_download_button)   # nối sau khi tích sẵn (nút Tải chưa được tạo)
            rows_layout.addWidget(row)
            self.rows.append(row)
        rows_layout.addStretch()
        scroll.setWidget(holder)
        layout.addWidget(scroll, stretch=1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        # Bước ③: hướng dẫn sau khi tải xong
        self.done_panel = QLabel()
        self.done_panel.setObjectName("Card")
        self.done_panel.setWordWrap(True)
        self.done_panel.setMargin(12)
        self.done_panel.setVisible(False)
        layout.addWidget(self.done_panel)

        buttons = QHBoxLayout()
        self.btn_recheck = QPushButton(btn_text("🔄 Kiểm tra lại"))
        self.btn_recheck.setObjectName("GhostBtn")
        self.btn_recheck.clicked.connect(self._refresh_runtime_label)
        buttons.addWidget(self.btn_recheck)
        buttons.addStretch()
        self.btn_test = QPushButton(btn_text("🔊 Nghe thử ngay" if kind == "tts" else "🧪 Chạy thử ngay"))
        self.btn_test.setVisible(False)
        self.btn_test.clicked.connect(self.test_requested)
        buttons.addWidget(self.btn_test)
        self.btn_cancel = QPushButton(btn_text("Đóng"))
        self.btn_cancel.setObjectName("GhostBtn")
        self.btn_cancel.clicked.connect(self._on_cancel_or_close)
        buttons.addWidget(self.btn_cancel)
        self.btn_download = QPushButton()
        self.btn_download.setObjectName("PrimaryBtn")
        self.btn_download.clicked.connect(self._on_download_clicked)
        buttons.addWidget(self.btn_download)
        layout.addLayout(buttons)

        self._refresh_runtime_label()
        self._update_download_button()

    # ---------- trạng thái ----------
    def selected_models(self) -> list[OfflineVoiceModel]:
        return [r.model for r in self.rows if r.check.isChecked() and r.check.isEnabled()]

    def _runtime_ready_or_downloadable(self) -> bool:
        return find_runtime_executable(self.kind) is not None or runtime_for(self.kind).url is not None

    def _refresh_runtime_label(self) -> None:
        runtime = runtime_for(self.kind)
        if find_runtime_executable(self.kind):
            self.lbl_runtime.setText(f"<span style='color:{tk.TERTIARY};'>✅ Bộ chạy offline đã sẵn sàng.</span>")
        elif runtime.url:
            self.lbl_runtime.setText(
                f"<span style='color:{tk.TEXT_MUTED};'>ℹ️ Lần tải đầu tiên app sẽ tải thêm bộ chạy offline "
                f"(~{runtime.size_mb} MB).</span>")
        else:
            self.lbl_runtime.setText(f"<span style='color:{tk.WARNING};'>⚠️ {escape(runtime.manual_hint)}</span>")
        self._update_download_button()

    def _update_download_button(self, *_args) -> None:
        models = self.selected_models()
        total = sum(m.size_mb for m in models)
        self.btn_download.setText(btn_text(f"⬇️ Tải {len(models)} mô hình (~{total} MB)" if models else "⬇️ Tải về"))
        self.btn_download.setEnabled(bool(models) and not self._downloading and not self._deleting and self._runtime_ready_or_downloadable())

    def _on_delete_row(self, row: _ModelRow) -> None:
        if self._downloading or self._deleting:
            return
        answer = QMessageBox.question(self, "Xoá mô hình", f"Xoá “{row.model.title}” khỏi máy?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        if row.model.engine != "vieneu":
            delete_model(row.model)
            row.refresh()
            self._update_download_button()
            return
        # VieNeu: xoá ~1.4 GB (hàng chục nghìn file) → luồng nền, UI hiện "đang xoá" thay vì đứng
        self._deleting = True
        for r in self.rows:
            r.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.lbl_status.setText(f"Đang xoá “{escape(row.model.title)}”… (có thể mất vài chục giây)")
        self._update_download_button()
        spawn_background_task(self._delete_vieneu_row(row), "delete-vieneu-model")

    async def _delete_vieneu_row(self, row: _ModelRow) -> None:
        from src.core.vieneu_runtime_installer import uninstall_vieneu_async
        try:
            await uninstall_vieneu_async(row.model.id)
            self.lbl_status.setText("")
        except Exception as exc:
            self.lbl_status.setText(f"<span style='color:{tk.ERROR};'>❌ Xoá thất bại: {escape(str(exc))}</span>")
        finally:
            self._deleting = False
            self.progress.setVisible(False)
            for r in self.rows:
                r.setEnabled(True)
                r.refresh()
            self._update_download_button()

    # ---------- tải ----------
    def _on_download_clicked(self) -> None:
        models = self.selected_models()
        if not models or self._downloading:
            return
        self._downloading = True
        self._cancel = asyncio.Event()
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.done_panel.setVisible(False)
        self.btn_cancel.setText(btn_text("Huỷ tải"))
        for row in self.rows:
            row.setEnabled(False)
        self._update_download_button()
        spawn_background_task(self.run_downloads(models), f"download-voice-models-{self.kind}")

    def _on_progress(self, done: int, total: int, label: str) -> None:
        view = format_download_progress(done, total, label)
        if view.determinate:
            self.progress.setRange(0, 1000)
            self.progress.setValue(view.permille)
        else:
            self.progress.setRange(0, 0)   # thanh bận: không biết tổng
        self.lbl_status.setText(view.text)

    async def run_downloads(self, models: list[OfflineVoiceModel]) -> list[str]:
        finished: list[str] = []
        try:
            for index, model in enumerate(models, start=1):
                self.lbl_status.setText(f"({index}/{len(models)}) Chuẩn bị tải {model.title}…")
                await download_model(model, self._on_progress, self._cancel)
                finished.append(model.id)
            self.lbl_status.setText("")
        except DownloadCancelled:
            self.lbl_status.setText(f"<span style='color:{tk.WARNING};'>Đã huỷ tải. Bạn có thể tải lại bất cứ lúc nào.</span>")
        except Exception as exc:
            self.lbl_status.setText(
                f"<span style='color:{tk.ERROR};'>❌ Tải thất bại: {escape(str(exc))}<br>"
                f"Kiểm tra kết nối mạng rồi bấm Tải lại.</span>")
        finally:
            self._downloading = False
            self.progress.setVisible(False)
            self.btn_cancel.setText(btn_text("Đóng"))
            for row in self.rows:
                row.setEnabled(True)
                row.refresh()
            self._refresh_runtime_label()
        if finished:
            self.models_ready.emit(finished)
            self._show_done_guide(finished)
        return finished

    def _show_done_guide(self, model_ids: list[str]) -> None:
        names = "".join(f"<li>{escape(r.model.title)}</li>" for r in self.rows if r.model.id in model_ids)
        if self.kind == "tts":
            next_steps = ("<li>✅ App đã chuyển chế độ sang <b>Trên máy (offline)</b> và điền sẵn giọng vừa tải.</li>"
                          "<li>👉 Bấm <b>🔊 Nghe thử ngay</b> để nghe Ted nói.</li>"
                          "<li>💾 Bấm <b>Lưu</b> ở mục Giọng nói để ghi nhớ cấu hình.</li>")
        else:
            next_steps = ("<li>✅ App đã chuyển chế độ sang <b>Trên máy (offline)</b> và chọn mô hình vừa tải.</li>"
                          "<li>👉 Bấm <b>🧪 Chạy thử ngay</b> để kiểm tra mô hình chạy được.</li>"
                          "<li>💾 Bấm <b>Lưu</b> ở mục Nhận giọng nói để ghi nhớ cấu hình.</li>")
        self.done_panel.setText(
            f"<p style='color:{tk.TERTIARY}; font-size:15px;'><b>🎉 Tải xong!</b></p><ul>{names}</ul>"
            f"<p><b>Bước tiếp theo:</b></p><ol>{next_steps}</ol>")
        self.done_panel.setVisible(True)
        self.btn_test.setVisible(True)

    def _on_cancel_or_close(self) -> None:
        if self._downloading and self._cancel is not None:
            self._cancel.set()
        else:
            self.accept()

    def reject(self) -> None:
        """Esc / nút Đóng khi đang tải = huỷ tải (giữ popup để người dùng thấy đã huỷ); không tải thì đóng."""
        if self._downloading and self._cancel is not None:
            self._cancel.set()
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self._cancel is not None:
            self._cancel.set()   # đóng cửa sổ giữa chừng = huỷ, file .part được dọn sạch
        super().closeEvent(event)
