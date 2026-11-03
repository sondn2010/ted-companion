"""Ma trận Eisenhower 2x2 (Q1..Q4) kiểu poster (ô nền màu + trục Khẩn cấp/Quan trọng) + dải "Chưa phân loại";
kéo-thả đổi ô / đổi thứ tự, ghi DB rồi dựng lại từ DB."""

import logging
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QMenu, QMessageBox, QVBoxLayout, QWidget

from src.core.i18n import tr
from src.core.models import db
from src.ui.dashboard_tabs.eisenhower_matrix_axes_board_widget import EisenhowerAxesBoard, QuadrantWatermarkCell
from src.ui.dashboard_tabs.task_delete_confirmation import confirm_and_delete_tasks
from src.ui.dashboard_tabs.task_filter_bar_widget import TaskFilterCriteria, task_matches
from src.ui.dashboard_tabs.eisenhower_quadrant_list_widget import (
    TASK_ID_ROLE,
    TASK_TITLE_ROLE,
    QuadrantListWidget,
)

logger = logging.getLogger(__name__)

QUADRANTS = (1, 2, 3, 4)


class EisenhowerMatrixViewWidget(QWidget):
    data_changed = Signal()
    task_activated = Signal(str, str)  # task_id, title (double-click → bắt đầu Pomodoro)
    edit_requested = Signal(str)  # task_id (chuột phải → Sửa)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cells: Dict[Optional[int], QuadrantListWidget] = {}
        self._titles: Dict[Optional[int], QLabel] = {}
        self._hints: Dict[Optional[int], QLabel] = {}
        self.watermarks: Dict[int, QuadrantWatermarkCell] = {}  # ô màu Q1..Q4: tiêu đề là chữ chìm nền
        self._criteria = TaskFilterCriteria()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        self.board = EisenhowerAxesBoard({q: self._build_cell(q) for q in QUADRANTS})
        root.addWidget(self.board, stretch=1)
        unsorted = self._build_cell(None)
        unsorted.setMaximumHeight(140)
        root.addWidget(unsorted)
        self.retranslate_ui()

    def _build_cell(self, quadrant: Optional[int]) -> QFrame:
        key = "unsorted" if quadrant is None else f"q{quadrant}"
        frame = QFrame() if quadrant is None else QuadrantWatermarkCell()
        frame.setObjectName("QuadrantCell")
        frame.setProperty("quadrant", key)
        lay = QVBoxLayout(frame)
        lw = QuadrantListWidget(quadrant, horizontal=quadrant is None)
        lw.task_dropped.connect(self.apply_drop)
        lw.itemDoubleClicked.connect(lambda item: self.task_activated.emit(
            item.data(TASK_ID_ROLE), item.data(TASK_TITLE_ROLE)))
        lw.customContextMenuRequested.connect(lambda pos, w=lw: self._on_context_menu(w, pos))
        self.cells[quadrant] = lw
        if quadrant is not None:  # ô màu: danh sách trong suốt phủ cả ô (vùng thả rộng), tiêu đề vẽ chìm phía sau
            lay.setContentsMargins(8, 8, 8, 8)
            lay.addWidget(lw)
            self.watermarks[quadrant] = frame
            if quadrant == 4:
                frame.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                frame.customContextMenuRequested.connect(
                    lambda pos, w=lw, f=frame: self._show_q4_context_menu(w, w.mapFromGlobal(f.mapToGlobal(pos)))
                )
            return frame
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(2)
        title = QLabel()
        title.setObjectName("QuadrantTitle")
        title.setProperty("quadrant", key)
        hint = QLabel()
        hint.setObjectName("QuadrantHint")
        hint.setProperty("quadrant", key)
        hint.setWordWrap(True)
        for w in (title, hint):
            lay.addWidget(w)
        lay.addSpacing(6)
        lay.addWidget(lw, stretch=1)
        self._titles[quadrant] = title
        self._hints[quadrant] = hint
        return frame

    def retranslate_ui(self):
        for q, cell in self.watermarks.items():
            cell.set_watermark(f"{tr(f'matrix_q{q}_title').upper()} · {self.cells[q].count()}", tr(f"matrix_q{q}_hint"))
        self._titles[None].setText(f"{tr('matrix_unsorted_title')} ({self.cells[None].count()})")
        self._hints[None].setText(tr("matrix_unsorted_hint"))

    # ── dữ liệu ──────────────────────────────────────────────────────────────
    def set_filter(self, criteria: TaskFilterCriteria):
        """Thanh lọc của tab Công việc (bỏ qua trạng thái: ma trận chỉ hiện việc đang mở)."""
        self._criteria = criteria
        self.refresh()

    def refresh(self):
        try:
            tasks = [t for t in db.list_tasks(include_done=False)
                     if t.status in ("todo", "in_progress") and task_matches(t, self._criteria, ignore_status=True)]
        except Exception:
            logger.exception("Không tải được việc cho ma trận Eisenhower")
            return
        tasks.sort(key=lambda t: (t.matrix_order, t.updated_at))
        selected = {q: (w.currentItem().data(TASK_ID_ROLE) if w.currentItem() else None) for q, w in self.cells.items()}
        for w in self.cells.values():
            w.blockSignals(True)
            w.clear()
        for t in tasks:
            lw = self.cells.get(t.quadrant if t.quadrant in QUADRANTS else None)
            if t.category == "parked_idea":
                icon = "🅿️ "
            elif t.status == "in_progress":
                icon = "▶️ "
            elif t.status == "done":
                icon = "✅ "
            else:
                icon = "📋 "
            text = f"{icon}{t.title}  🍅 {t.completed_pomodoros}/{t.estimated_pomodoros}"
            item = lw.add_task_item(t.id, text, t.title, tooltip=t.title)
            if selected.get(lw.quadrant) == t.id:
                lw.setCurrentItem(item)
        for w in self.cells.values():
            w.blockSignals(False)
        self.retranslate_ui()  # cập nhật số lượng trong tiêu đề

    def _quadrant_of(self, task_id: str) -> Optional[int]:
        for q, lw in self.cells.items():
            if task_id in lw.task_ids():
                return q
        return None

    def apply_drop(self, task_id: str, quadrant: Optional[int], ordered_ids: List[str]):
        """Ghi DB cho cột đích (và cột nguồn nếu khác), rồi dựng lại các ô từ DB."""
        try:
            source_q = self._quadrant_of(task_id)
            db.set_task_quadrant(task_id, quadrant, order=ordered_ids.index(task_id) if task_id in ordered_ids else None)
            db.reorder_quadrant(quadrant, ordered_ids)
            if source_q != quadrant and source_q in self.cells:
                db.reorder_quadrant(source_q, [i for i in self.cells[source_q].task_ids() if i != task_id])
        except Exception:
            logger.exception("Không lưu được vị trí task %s", task_id)
        self.refresh()
        self.data_changed.emit()

    def move_to_quadrant(self, task_id: str, quadrant: Optional[int]):
        """Chuyển task vào cuối ô đích (dùng cho menu chuột phải)."""
        ids = [i for i in self.cells[quadrant].task_ids() if i != task_id] + [task_id]
        self.apply_drop(task_id, quadrant, ids)

    def complete_task(self, task_id: str):
        self._safe(lambda: db.mark_task_done(task_id))

    def delete_task(self, task_id: str):
        """Hỏi xác nhận rồi xoá (menu chuột phải)."""
        items = (lw.item(i) for lw in self.cells.values() for i in range(lw.count()))
        title = next((it.data(TASK_TITLE_ROLE) for it in items if it.data(TASK_ID_ROLE) == task_id), task_id)
        if confirm_and_delete_tasks(self, [(task_id, title)]):
            self.refresh()
            self.data_changed.emit()

    def move_to_rock(self, task_id: str):
        self._safe(lambda: db.move_task_to_rock(task_id))

    def _safe(self, action):
        try:
            action()
        except Exception:
            logger.exception("Thao tác task thất bại")
        self.refresh()
        self.data_changed.emit()

    # ── menu chuột phải ──────────────────────────────────────────────────────
    def build_context_menu(self, task_id: str) -> QMenu:
        menu = QMenu(self)
        menu.addAction(tr("matrix_menu_edit"), lambda: self.edit_requested.emit(task_id))
        menu.addAction(tr("matrix_menu_done"), lambda: self.complete_task(task_id))
        menu.addAction(tr("matrix_menu_move_to_rock"), lambda: self.move_to_rock(task_id))
        menu.addAction(tr("matrix_menu_delete"), lambda: self.delete_task(task_id))
        menu.addSeparator()
        for q in QUADRANTS:
            label = tr("matrix_menu_move_to", q=q, title=tr(f"matrix_q{q}_title"))
            menu.addAction(label, lambda q=q: self.move_to_quadrant(task_id, q))
        menu.addAction(tr("matrix_menu_move_unsorted"), lambda: self.move_to_quadrant(task_id, None))
        return menu

    def delete_all_q4_tasks(self):
        """Xoá toàn bộ công việc trong phần Không quan trọng, không khẩn cấp (Q4)."""
        lw = self.cells.get(4)
        task_items = []
        if lw:
            for i in range(lw.count()):
                it = lw.item(i)
                task_items.append((it.data(TASK_ID_ROLE), it.data(TASK_TITLE_ROLE)))

        if not task_items:
            db_tasks = [t for t in db.list_tasks(include_done=True) if t.quadrant == 4]
            task_items = [(t.id, t.title) for t in db_tasks]

        if not task_items:
            QMessageBox.information(
                self,
                tr("matrix_q4_title"),
                tr("matrix_q4_empty")
            )
            return

        question = tr("matrix_q4_delete_all_confirm", count=len(task_items))
        answer = QMessageBox.question(
            self,
            tr("tasks_delete_confirm_title"),
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            db.delete_tasks([task_id for task_id, _ in task_items])
            self.refresh()
            self.data_changed.emit()
        except Exception:
            logger.exception("Xoá toàn bộ task Q4 thất bại")
            QMessageBox.warning(self, tr("tasks_delete_confirm_title"), tr("tasks_delete_error"))

    def _show_q4_context_menu(self, lw: QuadrantListWidget, pos):
        menu = QMenu(self)
        count = lw.count()
        label = tr("matrix_menu_delete_all_q4") + (f" ({count})" if count > 0 else "")
        action = menu.addAction(label, self.delete_all_q4_tasks)
        if count == 0:
            action.setEnabled(False)
        menu.exec(lw.viewport().mapToGlobal(pos))

    def _on_context_menu(self, lw: QuadrantListWidget, pos):
        item = lw.itemAt(pos)
        if item is None:
            if lw.quadrant == 4:
                self._show_q4_context_menu(lw, pos)
            return
        menu = self.build_context_menu(item.data(TASK_ID_ROLE))
        if lw.quadrant == 4:
            menu.addSeparator()
            count = lw.count()
            label = tr("matrix_menu_delete_all_q4") + (f" ({count})" if count > 0 else "")
            action = menu.addAction(label, self.delete_all_q4_tasks)
            if count == 0:
                action.setEnabled(False)
        menu.exec(lw.viewport().mapToGlobal(pos))
