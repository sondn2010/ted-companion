"""Xoá 1 hoặc nhiều task sau khi hỏi xác nhận (dùng chung cho Danh sách và Ma trận Eisenhower)."""

import logging
from typing import Sequence

from PySide6.QtWidgets import QMessageBox, QWidget

from src.core.i18n import tr
from src.core.models import db

logger = logging.getLogger(__name__)


def confirm_and_delete_tasks(parent: QWidget, tasks: Sequence[tuple[str, str]]) -> bool:
    """tasks: (task_id, title). Hỏi "Xoá …?" (mặc định Không) → xoá trong 1 giao dịch. Trả True nếu đã xoá."""
    if not tasks:
        QMessageBox.information(parent, tr("tab_tasks"), tr("tasks_none_selected"))
        return False
    if len(tasks) == 1:
        question = tr("tasks_delete_confirm_one", title=tasks[0][1])
    else:
        question = tr("tasks_delete_confirm_many", n=len(tasks))
    answer = QMessageBox.question(
        parent, tr("tasks_delete_confirm_title"), question,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return False
    try:
        db.delete_tasks([task_id for task_id, _title in tasks])
    except Exception:
        logger.exception("Xoá task thất bại")
        QMessageBox.warning(parent, tr("tasks_delete_confirm_title"), tr("tasks_delete_error"))
        return False
    return True
