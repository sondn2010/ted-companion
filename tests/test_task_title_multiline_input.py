"""Kiểm thử ô nhập Tên công việc mở rộng 2-3 dòng trong popup chi tiết task."""

from PySide6.QtCore import Qt
from qt_offscreen_app_helper import get_qapp

from src.core.models import db
from src.ui.task_detail_edit_dialog import TaskDetailEditDialog, TaskTitleInput


def test_task_title_input_dimensions_and_properties():
    get_qapp()
    inp = TaskTitleInput("Việc rất dài cần mô tả chi tiết")
    assert inp.height() == 65 or inp.maximumHeight() == 65
    assert inp.text() == "Việc rất dài cần mô tả chi tiết"

    inp.setText("Tiêu đề dòng 1\nTiêu đề dòng 2")
    assert "dòng 1" in inp.text() and "dòng 2" in inp.text()


def test_dialog_uses_multiline_title_input():
    get_qapp()
    task = db.add_task("Test task")
    dialog = TaskDetailEditDialog(task.id)

    assert isinstance(dialog.txt_title, TaskTitleInput)
    assert dialog.txt_title.height() >= 60
    assert dialog.width() >= 480 or dialog.minimumWidth() >= 480

    dialog.txt_title.setText("Việc quan trọng cần hoàn thành sớm\nChú ý hạn chót!")
    dialog.btn_save.click()

    stored = db.get_task(task.id)
    assert "Việc quan trọng" in stored.title


def test_shift_enter_inserts_single_newline_and_enter_submits():
    from PySide6.QtTest import QTest
    get_qapp()
    inp, hits = TaskTitleInput("ab"), []
    inp.returnPressed.connect(lambda: hits.append(1))
    inp.moveCursor(inp.textCursor().MoveOperation.End)
    QTest.keyClick(inp, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert inp.text() == "ab\n" and hits == []   # hồi quy: từng chèn 2 dòng mới
    QTest.keyClick(inp, Qt.Key.Key_Return)
    assert inp.text() == "ab\n" and hits == [1]
