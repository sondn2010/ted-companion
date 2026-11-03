"""Danh sách một ô Eisenhower: kéo-thả giữa các ô và sắp xếp lại trong ô (item data = task_id)."""

from typing import List, Optional

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget, QListWidgetItem

TASK_ID_ROLE = Qt.ItemDataRole.UserRole
TASK_TITLE_ROLE = Qt.ItemDataRole.UserRole + 1


class QuadrantListWidget(QListWidget):
    """quadrant: 1..4 hoặc None (Chưa phân loại).

    dropEvent KHÔNG để Qt tự di chuyển item (dễ nhân đôi/mất item giữa 2 list): chỉ tính thứ tự mới,
    báo `task_dropped` và để matrix ghi DB rồi dựng lại toàn bộ ô từ DB.
    """

    task_dropped = Signal(str, object, list)  # task_id, quadrant (int|None), ordered_ids của cột đích

    def __init__(self, quadrant: Optional[int], horizontal: bool = False, parent=None):
        super().__init__(parent)
        self.quadrant = quadrant
        self._horizontal = horizontal
        self.setObjectName("QuadrantList")
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        if horizontal:
            self.setFlow(QListView.Flow.LeftToRight)
            self.setWrapping(True)
            self.setResizeMode(QListView.ResizeMode.Adjust)

    def task_ids(self) -> List[str]:
        return [self.item(i).data(TASK_ID_ROLE) for i in range(self.count())]

    def add_task_item(self, task_id: str, text: str, title: str, tooltip: str = "") -> QListWidgetItem:
        item = QListWidgetItem(text)
        item.setData(TASK_ID_ROLE, task_id)
        item.setData(TASK_TITLE_ROLE, title)
        item.setToolTip(tooltip or title)
        self.addItem(item)
        return item

    # ── drag & drop ──────────────────────────────────────────────────────────
    def _insert_row_at(self, pos: QPoint) -> int:
        """Vị trí chèn theo toạ độ thả: nửa sau của item → chèn sau item đó; ngoài item → cuối danh sách."""
        item = self.itemAt(pos)
        if item is None:
            return self.count()
        rect = self.visualItemRect(item)
        after = pos.x() > rect.center().x() if self._horizontal else pos.y() > rect.center().y()
        return self.row(item) + (1 if after else 0)

    @staticmethod
    def _dragged_task_id(source) -> Optional[str]:
        if not isinstance(source, QuadrantListWidget):
            return None
        item = (source.selectedItems() or [source.currentItem()])[0]
        return item.data(TASK_ID_ROLE) if item is not None else None

    def dragEnterEvent(self, event):
        if isinstance(event.source(), QuadrantListWidget):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if isinstance(event.source(), QuadrantListWidget):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        task_id = self._dragged_task_id(event.source())
        if task_id is None:
            event.ignore()
            return
        row = self._insert_row_at(event.position().toPoint())
        ids = self.task_ids()
        if task_id in ids:  # kéo trong cùng ô: bỏ vị trí cũ, chỉnh chỉ số chèn
            old = ids.index(task_id)
            ids.remove(task_id)
            if old < row:
                row -= 1
        ids.insert(max(0, min(row, len(ids))), task_id)
        # IgnoreAction: nguồn không tự xoá item; phát tín hiệu sau khi vòng drag kết thúc để refresh an toàn
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()
        quadrant = self.quadrant
        QTimer.singleShot(0, self, lambda: self.task_dropped.emit(task_id, quadrant, ids))  # context=self: widget huỷ thì không emit
