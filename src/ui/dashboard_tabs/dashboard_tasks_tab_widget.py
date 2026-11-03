import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from src.config import settings
from src.core.i18n import i18n, tr
from src.core.models import db
from src.ui.button_text_escape import btn_text
from src.ui.dashboard_tabs.eisenhower_matrix_view_widget import EisenhowerMatrixViewWidget
from src.ui.dashboard_tabs.task_delete_confirmation import confirm_and_delete_tasks
from src.ui.dashboard_tabs.task_filter_bar_widget import TaskFilterBar, task_matches
from src.ui.meeting_mode.meeting_entry_point_helpers import meeting_active, request_meeting_toggle
from src.ui.task_detail_edit_dialog import TaskDetailEditDialog

logger = logging.getLogger(__name__)

VIEW_SETTING_KEY = "tasks_view"  # khoá mở rộng trong settings.json: "matrix" | "list"


class TaskTableWidgetItem(QTableWidgetItem):
    """Item cho bảng task, đồng bộ trạng thái chọn trên toàn bộ các ô trong cùng dòng."""

    def setSelected(self, select: bool):
        super().setSelected(select)
        tbl = self.tableWidget()
        if tbl is not None:
            r = self.row()
            for col in range(tbl.columnCount()):
                it = tbl.item(r, col)
                if it is not None and it is not self:
                    QTableWidgetItem.setSelected(it, select)


class TaskTableWidget(QTableWidget):
    """Bảng hiển thị danh sách công việc đa cột, tương thích với các API danh sách cũ."""

    def count(self) -> int:
        return self.rowCount()

    def item(self, row: int, column: int = 0) -> Optional[QTableWidgetItem]:
        return super().item(row, column)

    def currentItem(self) -> Optional[QTableWidgetItem]:
        curr = super().currentItem()
        if curr is None:
            return None
        return self.item(curr.row(), 0) or curr

    def selectedItems(self) -> list:
        selected_rows = sorted({idx.row() for idx in self.selectedIndexes()})
        return [self.item(r, 0) for r in selected_rows if self.item(r, 0) is not None]

    def clear(self):
        self.setRowCount(0)

    def addItem(self, item):
        row = self.rowCount()
        self.insertRow(row)
        if isinstance(item, QTableWidgetItem):
            self.setItem(row, 0, item)
        else:
            tbl_item = TaskTableWidgetItem(item.text())
            tbl_item.setData(Qt.ItemDataRole.UserRole, item.data(Qt.ItemDataRole.UserRole))
            tbl_item.setData(Qt.ItemDataRole.UserRole + 1, item.data(Qt.ItemDataRole.UserRole + 1))
            self.setItem(row, 0, tbl_item)


class DashboardTasksTabWidget(QWidget):
    """Tab 1: Tasks & Distraction Parking Lot (chốt việc đầu ngày, khởi chạy Pomodoro cho từng Task)."""

    data_changed = Signal()  # báo shell refresh các tab khác (analytics...)

    def __init__(self, focus_engine, parent=None):
        super().__init__(parent)
        self.focus_engine = focus_engine
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Tiêu đề + nút ＋ (popup Thêm công việc đầy đủ trường)
        title_row = QHBoxLayout()
        self.title_lbl = QLabel(tr("tasks_title"))
        self.title_lbl.setObjectName("TitleLabel")
        title_row.addWidget(self.title_lbl)
        title_row.addStretch()
        self.btn_add = QPushButton("＋")
        self.btn_add.setObjectName("FabBtn")
        self.btn_add.setToolTip(tr("tasks_btn_add"))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self.open_task_creator)
        title_row.addWidget(self.btn_add)
        layout.addLayout(title_row)

        # Chọn kiểu xem: Danh sách | Ma trận Eisenhower, rồi thanh lọc dùng chung
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(8)
        self.btn_view_matrix = self._make_view_button("tasks_view_matrix")
        self.btn_view_list = self._make_view_button("tasks_view_list")
        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        for btn in (self.btn_view_list, self.btn_view_matrix):
            self.view_group.addButton(btn)
            toggle_row.addWidget(btn)
        toggle_row.addSpacing(8)
        self.filter_bar = TaskFilterBar()
        self.filter_bar.changed.connect(self.refresh)
        toggle_row.addWidget(self.filter_bar, stretch=1)
        layout.addLayout(toggle_row)

        self.view_stack = QStackedWidget()
        layout.addWidget(self.view_stack, stretch=1)

        # Trang 0: danh sách công việc dạng bảng đa cột
        list_page = QWidget()
        list_layout = QVBoxLayout(list_page)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(16)
        self.task_list = TaskTableWidget()
        self.task_list.setColumnCount(7)
        self.task_list.setHorizontalHeaderLabels([
            tr("tasks_col_status"),
            tr("tasks_col_title"),
            tr("tasks_col_eisenhower"),
            tr("tasks_col_category"),
            tr("tasks_col_pomodoro"),
            tr("tasks_col_date"),
            tr("tasks_col_notes"),
        ])
        self.task_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.task_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)  # Ctrl/Shift → chọn nhiều
        self.task_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.task_list.verticalHeader().setVisible(False)
        self.task_list.setAlternatingRowColors(True)
        self.task_list.setShowGrid(False)
        header = self.task_list.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.task_list.itemDoubleClicked.connect(lambda item: self.open_task_editor(item.data(Qt.ItemDataRole.UserRole)))
        self.task_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.task_list.customContextMenuRequested.connect(self._on_task_list_context_menu)
        self.task_list.itemSelectionChanged.connect(self._update_delete_button)
        delete_key = QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self.task_list)
        delete_key.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete_key.activated.connect(self._on_delete_selected_task)
        list_layout.addWidget(self.task_list, stretch=1)
        self.lbl_list_hint = QLabel(tr("tasks_list_hint"))
        self.lbl_list_hint.setObjectName("MutedLabel")
        list_layout.addWidget(self.lbl_list_hint)

        action_row = QHBoxLayout()
        self.btn_start_pomo = QPushButton(btn_text(tr("tasks_btn_start_pomo")))
        self.btn_start_pomo.setObjectName("PrimaryBtn")
        self.btn_start_pomo.clicked.connect(self._on_start_selected_task)

        self.btn_edit = QPushButton(btn_text(tr("tasks_btn_edit")))
        self.btn_edit.clicked.connect(self._on_edit_selected_task)

        self.btn_toggle_done = QPushButton(btn_text(tr("tasks_btn_toggle_done")))
        self.btn_toggle_done.clicked.connect(self._on_toggle_selected_task)

        self.btn_delete = QPushButton(btn_text(tr("tasks_btn_delete")))
        self.btn_delete.setObjectName("DangerBtn")
        self.btn_delete.clicked.connect(self._on_delete_selected_task)

        action_row.addWidget(self.btn_start_pomo)
        self.btn_meeting = QPushButton(btn_text(tr("tasks_btn_start_meeting")))   # Họp / Học nhóm (thay Deep Work)
        self.btn_meeting.clicked.connect(lambda: request_meeting_toggle(self.focus_engine))
        action_row.addWidget(self.btn_meeting)
        if hasattr(self.focus_engine, "state_changed"):   # nhãn Họp ⇄ Kết thúc theo trạng thái
            self.focus_engine.state_changed.connect(lambda *_: self._update_meeting_button())
        self._update_meeting_button()
        action_row.addWidget(self.btn_edit)
        action_row.addWidget(self.btn_toggle_done)
        self.btn_move_to_rock = QPushButton(btn_text(tr("tasks_btn_move_to_rock")))
        self.btn_move_to_rock.clicked.connect(self._on_move_selected_to_rock)
        action_row.addWidget(self.btn_move_to_rock)
        action_row.addStretch()
        action_row.addWidget(self.btn_delete)
        list_layout.addLayout(action_row)
        self.view_stack.addWidget(list_page)

        # Trang 1: ma trận Eisenhower (kéo-thả)
        self.matrix_view = EisenhowerMatrixViewWidget()
        self.matrix_view.data_changed.connect(self.data_changed)
        self.matrix_view.task_activated.connect(self._on_matrix_task_activated)
        self.matrix_view.edit_requested.connect(self.open_task_editor)
        self.view_stack.addWidget(self.matrix_view)

        self.btn_view_list.clicked.connect(lambda: self._set_view("list"))
        self.btn_view_matrix.clicked.connect(lambda: self._set_view("matrix"))
        self._set_view(self._load_view(), persist=False)

        i18n.language_changed.connect(lambda _: self.retranslate_ui())

    # ── chuyển kiểu xem ──────────────────────────────────────────────────────
    @staticmethod
    def _make_view_button(key: str) -> QPushButton:
        btn = QPushButton(btn_text(tr(key)))
        btn.setObjectName("SegmentBtn")
        btn.setCheckable(True)
        return btn

    @staticmethod
    def _load_view() -> str:
        try:
            value = settings._extra.get(VIEW_SETTING_KEY)
        except Exception:
            logger.exception("Không đọc được kiểu xem Tasks")
            return "matrix"
        return value if value in ("list", "matrix") else "matrix"

    def _set_view(self, view: str, persist: bool = True):
        is_matrix = view == "matrix"
        self.view_stack.setCurrentIndex(1 if is_matrix else 0)
        self.filter_bar.set_status_visible(not is_matrix)
        for btn, active in ((self.btn_view_matrix, is_matrix), (self.btn_view_list, not is_matrix)):
            btn.setChecked(active)
            btn.setProperty("active", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if persist:
            try:
                settings._extra[VIEW_SETTING_KEY] = view
                settings.save()
            except Exception:
                logger.exception("Không lưu được kiểu xem Tasks")

    def show_list(self, task_id: Optional[str] = None):
        """Chuyển sang Danh sách (từ menu pet / nút "Xem Bãi đỗ"); task_id có thì chọn sẵn dòng đó
        (bộ lọc đang ẩn task đó → bỏ lọc để thấy được)."""
        self._set_view("list")
        if task_id and self._select_task(task_id) is None:
            self.filter_bar.show_everything()
            self._select_task(task_id)

    def _select_task(self, task_id: str) -> Optional[QTableWidgetItem]:
        for i in range(self.task_list.count()):
            item = self.task_list.item(i, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == task_id:
                self.task_list.selectRow(i)
                self.task_list.setCurrentItem(item)
                self.task_list.scrollToItem(item)
                for col in range(self.task_list.columnCount()):
                    c_it = self.task_list.item(i, col)
                    if c_it:
                        c_it.setSelected(True)
                return item
        return None

    def current_view(self) -> str:
        return "matrix" if self.view_stack.currentIndex() == 1 else "list"

    def _on_matrix_task_activated(self, task_id: str, title: str):
        self.focus_engine.start_focus_session(
            task_title=title, duration_mins=settings.default_pomodoro_mins, task_id=task_id
        )

    def _update_meeting_button(self):
        self.btn_meeting.setText(btn_text(tr("tasks_btn_stop_meeting" if meeting_active(self.focus_engine)
                                             else "tasks_btn_start_meeting")))

    def retranslate_ui(self):
        self.title_lbl.setText(tr("tasks_title"))
        self.btn_add.setToolTip(tr("tasks_btn_add"))
        self.filter_bar.retranslate_ui()
        self.task_list.setHorizontalHeaderLabels([
            tr("tasks_col_status"),
            tr("tasks_col_title"),
            tr("tasks_col_eisenhower"),
            tr("tasks_col_category"),
            tr("tasks_col_pomodoro"),
            tr("tasks_col_date"),
            tr("tasks_col_notes"),
        ])
        self.lbl_list_hint.setText(tr("tasks_list_hint"))
        self.btn_start_pomo.setText(btn_text(tr("tasks_btn_start_pomo")))
        self._update_meeting_button()
        self.btn_edit.setText(btn_text(tr("tasks_btn_edit")))
        self.btn_toggle_done.setText(btn_text(tr("tasks_btn_toggle_done")))
        self.btn_move_to_rock.setText(btn_text(tr("tasks_btn_move_to_rock")))
        self._update_delete_button()
        self.btn_view_matrix.setText(btn_text(tr("tasks_view_matrix")))
        self.btn_view_list.setText(btn_text(tr("tasks_view_list")))
        self.matrix_view.retranslate_ui()

    def refresh(self):
        """Dựng lại Danh sách theo bộ lọc (giữ các dòng đang chọn) và Ma trận."""
        criteria = self.filter_bar.criteria()
        selected = {item.data(Qt.ItemDataRole.UserRole) for item in self.task_list.selectedItems()}
        self.task_list.blockSignals(True)
        self.task_list.clear()
        for t in db.list_tasks(include_done=True):
            if not task_matches(t, criteria):
                continue
            row = self.task_list.rowCount()
            self.task_list.insertRow(row)

            # 1. Trạng thái
            if t.status == "done":
                status_text = tr("task_detail_status_done")
            elif t.status == "in_progress":
                status_text = tr("task_detail_status_in_progress")
            elif t.status == "archived":
                status_text = tr("task_detail_status_archived")
            else:
                status_text = tr("task_detail_status_todo")

            # 2. Tiêu đề
            title_text = t.title

            # 3. Ma trận Eisenhower
            if t.quadrant == 1:
                quad_text = f"🔥 Q1: {tr('matrix_q1_title').replace('🔥 ', '')}"
            elif t.quadrant == 2:
                quad_text = f"⭐ Q2: {tr('matrix_q2_title').replace('⭐ ', '')}"
            elif t.quadrant == 3:
                quad_text = f"⚡ Q3: {tr('matrix_q3_title').replace('⚡ ', '')}"
            elif t.quadrant == 4:
                quad_text = f"🗑️ Q4: {tr('matrix_q4_title').replace('🗑️ ', '')}"
            else:
                quad_text = "—"

            # 4. Phân loại
            if t.category == "parked_idea":
                cat_text = tr("tasks_cat_parked_idea")
            elif t.category == "shallow_work":
                cat_text = tr("tasks_cat_shallow_work")
            else:
                cat_text = tr("tasks_cat_deep_work")

            # 5. Pomodoro
            pomo_text = f"🍅 {t.completed_pomodoros}/{t.estimated_pomodoros}"

            # 6. Ngày hẹn
            date_text = str(t.scheduled_date) if t.scheduled_date else "—"

            # 7. Ghi chú
            notes_text = (t.notes or "").strip()
            notes_display = (notes_text[:40] + "...") if len(notes_text) > 40 else (notes_text or "—")

            col_values = [
                status_text,
                title_text,
                quad_text,
                cat_text,
                pomo_text,
                date_text,
                notes_display,
            ]

            for col, val in enumerate(col_values):
                item = TaskTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, t.id)
                item.setData(Qt.ItemDataRole.UserRole + 1, t.title)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                if col == 1:
                    item.setToolTip(t.title)
                elif col == 6 and notes_text:
                    item.setToolTip(notes_text)
                self.task_list.setItem(row, col, item)

            if t.id in selected:
                for col in range(self.task_list.columnCount()):
                    it = self.task_list.item(row, col)
                    if it:
                        it.setSelected(True)

        self.task_list.blockSignals(False)
        self._update_delete_button()
        self.matrix_view.set_filter(criteria)

    def _selected_items(self) -> list:
        """Các dòng đang chọn theo thứ tự hiển thị."""
        return sorted(self.task_list.selectedItems(), key=self.task_list.row)

    def _first_selected(self) -> Optional[QTableWidgetItem]:
        items = self._selected_items()
        if not items:
            QMessageBox.information(self, tr("tab_tasks"), tr("tasks_none_selected"))
            return None
        return items[0]

    def _update_delete_button(self):
        count = len(self.task_list.selectedItems())
        self.btn_delete.setText(btn_text(tr("tasks_btn_delete") + (f" ({count})" if count > 1 else "")))

    def _on_start_selected_task(self):
        item = self._first_selected()
        if item is None:
            return
        self.focus_engine.start_focus_session(
            task_title=item.data(Qt.ItemDataRole.UserRole + 1),
            duration_mins=settings.default_pomodoro_mins,
            task_id=item.data(Qt.ItemDataRole.UserRole),
        )

    def _on_edit_selected_task(self):
        item = self._first_selected()
        if item is not None:
            self.open_task_editor(item.data(Qt.ItemDataRole.UserRole))

    def open_task_editor(self, task_id: Optional[str]) -> TaskDetailEditDialog:
        """Popup xem/sửa task (task_id=None → thêm mới); lưu xong báo shell refresh (danh sách + ma trận + tab khác)."""
        dialog = TaskDetailEditDialog(task_id, focus_engine=self.focus_engine, parent=self)
        dialog.task_saved.connect(lambda _id: self.data_changed.emit())
        dialog.show()
        return dialog

    def _on_move_selected_to_rock(self):
        items = self._selected_items()
        if not items:
            QMessageBox.information(self, tr("tab_tasks"), tr("tasks_none_selected"))
            return
        for item in items:
            task_id = item.data(Qt.ItemDataRole.UserRole)
            db.move_task_to_rock(task_id)
        self.data_changed.emit()

    def _on_task_list_context_menu(self, pos):
        item = self.task_list.itemAt(pos)
        if item is None:
            return
        row = item.row()
        selected_rows = {it.row() for it in self.task_list.selectedItems()}
        if row not in selected_rows:
            self.task_list.selectRow(row)
        menu = QMenu(self)
        menu.addAction(btn_text(tr("tasks_btn_start_pomo")), self._on_start_selected_task)
        menu.addAction(btn_text(tr("tasks_btn_edit")), self._on_edit_selected_task)
        menu.addAction(btn_text(tr("tasks_btn_toggle_done")), self._on_toggle_selected_task)
        menu.addSeparator()
        menu.addAction(btn_text(tr("tasks_btn_move_to_rock")), self._on_move_selected_to_rock)
        menu.addSeparator()
        menu.addAction(btn_text(tr("tasks_btn_delete")), self._on_delete_selected_task)
        menu.exec(self.task_list.viewport().mapToGlobal(pos))

    def open_task_creator(self) -> TaskDetailEditDialog:
        return self.open_task_editor(None)

    def _on_toggle_selected_task(self):
        items = self._selected_items()
        for item in items:
            db.mark_task_done(item.data(Qt.ItemDataRole.UserRole))
        if items:
            self.data_changed.emit()

    def _on_delete_selected_task(self):
        tasks = [(i.data(Qt.ItemDataRole.UserRole), i.data(Qt.ItemDataRole.UserRole + 1)) for i in self._selected_items()]
        if confirm_and_delete_tasks(self, tasks):
            self.data_changed.emit()
