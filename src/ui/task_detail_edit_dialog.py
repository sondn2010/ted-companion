"""Popup "📋 Chi tiết công việc": xem + sửa thông tin một task; task_id=None → popup "➕ Thêm công việc" (nút ＋ ở tab Công việc).

Mở từ: link tên task trong bong bóng của Ted (nhắc việc lúc bắt đầu Deep Work), nút ✏️ Sửa / double-click ở
tab Công việc (Danh sách), chuột phải → Sửa ở Ma trận Eisenhower. Lưu xong phát `task_saved(task_id)`.
"""

import logging
from html import escape
from typing import Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.core.i18n import tr
from src.core.models import Task, db
from src.core.task_notes_merge_on_save import notes_to_save
from src.ui.button_text_escape import btn_text
from src.ui.theme import design_tokens as tk

logger = logging.getLogger("ted")

CATEGORIES = ("deep_work", "shallow_work", "parked_idea")
STATUSES = ("todo", "in_progress", "done", "archived")


def quadrant_text(quadrant: Optional[int]) -> str:
    if quadrant in (1, 2, 3, 4):
        return f"Q{quadrant} · {tr(f'matrix_q{quadrant}_title')}"
    return tr("matrix_unsorted_title")


def _combo(items: list[tuple[str, object]], current) -> QComboBox:
    combo = QComboBox()
    for text, data in items:
        combo.addItem(text, data)
    idx = combo.findData(current)
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    return combo


class TaskTitleInput(QPlainTextEdit):
    """Ô nhập tên task rộng rãi 2-3 dòng, hỗ trợ Enter để lưu, Shift+Enter xuống dòng."""
    returnPressed = Signal()

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setFixedHeight(65)  # 2-3 dòng
        self.setMinimumWidth(320)
        self.setTabChangesFocus(True)

    def text(self) -> str:
        return self.toPlainText()

    def setText(self, text: str) -> None:
        self.setPlainText(text)

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.returnPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)   # Shift+Enter → xuống dòng đúng 1 lần


class TaskDetailEditDialog(QDialog):
    task_saved = Signal(str)  # task_id

    def __init__(self, task_id: Optional[str], dashboard=None, focus_engine=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.task_id = task_id
        self._dashboard = dashboard
        self._focus_engine = focus_engine
        self._creating = task_id is None
        self.setWindowTitle(tr("task_create_title" if self._creating else "task_detail_title"))
        self.setMinimumWidth(480)
        self.setWindowFlags((self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
                            & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        root = QVBoxLayout(self)
        root.setSpacing(12)
        task = Task(title="") if self._creating else db.get_task(task_id)

        self.lbl_error = QLabel()
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()

        buttons = QHBoxLayout()
        self.btn_open_list = QPushButton(btn_text(tr("task_detail_btn_open_list")))
        self.btn_open_list.clicked.connect(self._open_in_tasks_tab)
        self.btn_open_list.setVisible(task is not None and dashboard is not None and not self._creating)
        buttons.addWidget(self.btn_open_list)
        self.btn_move_to_rock = QPushButton(btn_text(tr("tasks_btn_move_to_rock")))
        self.btn_move_to_rock.clicked.connect(self._on_move_to_rock)
        self.btn_move_to_rock.setVisible(task is not None and not self._creating)
        buttons.addWidget(self.btn_move_to_rock)
        buttons.addStretch()
        btn_close = QPushButton(btn_text(tr("task_detail_btn_close")))
        btn_close.clicked.connect(self.close)
        buttons.addWidget(btn_close)
        self.btn_save = QPushButton(btn_text(tr("task_create_btn" if self._creating else "task_detail_btn_save")))
        self.btn_save.setObjectName("PrimaryBtn")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save.setVisible(task is not None)
        buttons.addWidget(self.btn_save)

        if task is None:
            self._show_error(tr("task_detail_not_found"))
        else:
            root.addLayout(self._build_form(task))
        root.addWidget(self.lbl_error)
        root.addLayout(buttons)

    def _build_form(self, task: Task) -> QFormLayout:
        self.txt_title = TaskTitleInput(task.title)
        self.txt_title.returnPressed.connect(self._on_save)
        self.combo_status = _combo([(tr(f"task_detail_status_{s}"), s) for s in STATUSES], task.status)
        self.combo_quadrant = _combo([(quadrant_text(q), q) for q in (1, 2, 3, 4, None)], task.quadrant)
        self.combo_category = _combo([(tr(f"tasks_cat_{c}"), c) for c in CATEGORIES], task.category)
        self.spin_pomodoros = QSpinBox()
        self.spin_pomodoros.setRange(1, 12)
        self.spin_pomodoros.setValue(max(1, task.estimated_pomodoros))
        if not self._creating:
            self.spin_pomodoros.setPrefix(f"{task.completed_pomodoros} / ")
        self.spin_pomodoros.setSuffix(" 🍅")
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        parsed = QDate.fromString(task.scheduled_date or "", Qt.DateFormat.ISODate)
        self.date_edit.setDate(parsed if parsed.isValid() else QDate.currentDate())
        self.txt_notes = QPlainTextEdit(task.notes or "")   # ghi chú tự do; Gỡ Rối Ý Tưởng nối thêm vào đây
        self.txt_notes.setMaximumHeight(120)
        self._notes_loaded_raw = task.notes or ""
        self._notes_loaded_shown = self.txt_notes.toPlainText()

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        for key, field in (
            ("task_detail_name", self.txt_title),
            ("task_detail_status", self.combo_status),
            ("task_detail_quadrant", self.combo_quadrant),
            ("task_detail_category", self.combo_category),
            ("task_detail_pomodoros", self.spin_pomodoros),
            ("task_detail_date", self.date_edit),
            ("task_detail_notes", self.txt_notes),
        ):
            label = QLabel(tr(key))
            label.setObjectName("MutedLabel")
            if field in (self.txt_title, self.txt_notes):
                label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            form.addRow(label, field)
        if self._creating:  # việc mới luôn "Chưa làm"
            form.setRowVisible(self.combo_status, False)
        else:
            self.txt_title.selectAll()
        return form

    def _show_error(self, text: str) -> None:
        self.lbl_error.setText(f"<span style='color:{tk.ERROR};'>{escape(text)}</span>")
        self.lbl_error.show()

    def _on_save(self) -> None:
        if not self.txt_title.text().strip():
            self._show_error(tr("task_detail_empty_title"))
            self.txt_title.setFocus()
            return
        try:
            if self._creating and self.task_id is None:
                self.task_id = self._create_task()
            current = db.get_task(self.task_id)
            notes = notes_to_save(self._notes_loaded_raw, self._notes_loaded_shown, self.txt_notes.toPlainText(),
                                  (current.notes or "") if current else "")
            task = db.update_task(
                self.task_id,
                title=self.txt_title.text(),
                category=self.combo_category.currentData(),
                estimated_pomodoros=self.spin_pomodoros.value(),
                quadrant=self.combo_quadrant.currentData(),
                status=self.combo_status.currentData(),
                scheduled_date=self.date_edit.date().toString(Qt.DateFormat.ISODate),
                notes=notes,
            )
        except Exception:
            logger.exception("Không lưu được task %s", self.task_id)
            self._show_error(tr("task_detail_save_error"))
            return
        if task is None:
            self._show_error(tr("task_detail_not_found"))
            return
        # Đang chạy phiên Pomodoro của chính task này → đồng hồ hiện tên mới ngay
        focus = self._focus_engine
        if focus is not None and getattr(focus, "active_task_id", None) == self.task_id:
            focus.active_task_title = task.title
        self.task_saved.emit(self.task_id)
        self.close()

    def _on_move_to_rock(self) -> None:
        if not self.task_id:
            return
        try:
            db.move_task_to_rock(self.task_id)
        except Exception:
            logger.exception("Không chuyển được task %s sang Rock", self.task_id)
            self._show_error(tr("task_move_rock_error"))
            return
        focus = self._focus_engine
        if focus is not None and getattr(focus, "active_task_id", None) == self.task_id:
            focus.active_task_id = None
        self.task_saved.emit(self.task_id)
        self.close()

    def _create_task(self) -> str:
        """Qua FocusEngine.add_task (nếu có) để việc mới cũng được tự phân loại Eisenhower như Bãi đỗ;
        ô/ngày người dùng chọn được ghi đè ngay sau đó (bộ phân loại chỉ ghi khi còn Chưa phân loại)."""
        add = getattr(self._focus_engine, "add_task", None) or db.add_task
        return add(self.txt_title.text().strip(), category=self.combo_category.currentData(),
                   estimated_pomodoros=self.spin_pomodoros.value()).id

    def _open_in_tasks_tab(self) -> None:
        self.close()
        self._dashboard.open_tasks_list(self.task_id)
