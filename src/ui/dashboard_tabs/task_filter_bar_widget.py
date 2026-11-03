"""Thanh lọc task dùng chung cho Danh sách và Ma trận Eisenhower: tìm theo tên + Trạng thái + Loại + Ô Eisenhower.

Tìm tên không phân biệt hoa/thường và dấu tiếng Việt ("nop thue" khớp "Nộp thuế"). Ma trận chỉ hiện việc đang mở
nên bỏ qua lọc trạng thái (`ignore_status=True`).
"""

import unicodedata
from dataclasses import dataclass
from typing import Optional, Union

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QWidget

from src.core.i18n import tr

ANY = "any"
UNSORTED = "unsorted"
OPEN_STATUSES = ("todo", "in_progress")


@dataclass(frozen=True)
class TaskFilterCriteria:
    text: str = ""
    status: str = "open"                  # open | done | all
    category: str = ANY                   # any | deep_work | shallow_work | parked_idea
    quadrant: Union[int, str] = ANY       # any | unsorted | 1..4


def fold_text(text: str) -> str:
    """Bỏ dấu + chữ thường để tìm kiếm ("Đ" → "d")."""
    decomposed = unicodedata.normalize("NFD", (text or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").casefold().strip()


def task_matches(task, criteria: TaskFilterCriteria, ignore_status: bool = False) -> bool:
    if criteria.text and fold_text(criteria.text) not in fold_text(task.title):
        return False
    if not ignore_status:
        if criteria.status == "open" and task.status not in OPEN_STATUSES:
            return False
        if criteria.status == "done" and task.status != "done":
            return False
    if criteria.category != ANY and task.category != criteria.category:
        return False
    if criteria.quadrant == UNSORTED:
        return task.quadrant not in (1, 2, 3, 4)
    return criteria.quadrant == ANY or task.quadrant == criteria.quadrant


class TaskFilterBar(QWidget):
    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.txt_search = QLineEdit()
        self.txt_search.setObjectName("TaskSearchInput")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setMinimumWidth(200)
        self.combo_status = QComboBox()
        self.combo_category = QComboBox()
        self.combo_quadrant = QComboBox()
        row.addWidget(self.txt_search, stretch=1)
        for combo in (self.combo_status, self.combo_category, self.combo_quadrant):
            row.addWidget(combo)
            combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
        self.txt_search.textChanged.connect(lambda _t: self.changed.emit())
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.txt_search.setPlaceholderText(tr("filter_search_placeholder"))
        self._fill(self.combo_status, [(tr("filter_status_open"), "open"), (tr("filter_status_done"), "done"),
                                       (tr("filter_status_all"), "all")])
        self._fill(self.combo_category, [(tr("filter_category_all"), ANY)]
                   + [(tr(f"tasks_cat_{c}"), c) for c in ("deep_work", "shallow_work", "parked_idea")])
        self._fill(self.combo_quadrant, [(tr("filter_quadrant_all"), ANY)]
                   + [(f"Q{q} · {tr(f'matrix_q{q}_title')}", q) for q in (1, 2, 3, 4)]
                   + [(tr("matrix_unsorted_title"), UNSORTED)])

    @staticmethod
    def _fill(combo: QComboBox, items) -> None:
        """Đổi chữ (đổi ngôn ngữ) mà giữ lựa chọn hiện tại, không phát changed."""
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for text, data in items:
            combo.addItem(text, data)
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def set_status_visible(self, visible: bool) -> None:
        """Ma trận chỉ hiện việc đang mở → ẩn ô Trạng thái cho đỡ gây hiểu nhầm."""
        self.combo_status.setVisible(visible)

    def show_everything(self) -> None:
        """Bỏ mọi điều kiện (mọi trạng thái) — dùng khi cần chọn một task đang bị lọc ẩn."""
        for widget in (self.txt_search, self.combo_status, self.combo_category, self.combo_quadrant):
            widget.blockSignals(True)
        self.txt_search.clear()
        self.combo_status.setCurrentIndex(self.combo_status.findData("all"))
        self.combo_category.setCurrentIndex(0)
        self.combo_quadrant.setCurrentIndex(0)
        for widget in (self.txt_search, self.combo_status, self.combo_category, self.combo_quadrant):
            widget.blockSignals(False)
        self.changed.emit()

    def criteria(self) -> TaskFilterCriteria:
        return TaskFilterCriteria(
            text=self.txt_search.text().strip(),
            status=self.combo_status.currentData() or "open",
            category=self.combo_category.currentData() or ANY,
            quadrant=self.combo_quadrant.currentData() if self.combo_quadrant.currentData() is not None else ANY,
        )
