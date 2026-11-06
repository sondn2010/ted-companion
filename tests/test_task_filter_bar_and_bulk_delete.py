"""Thanh lọc task (tên không dấu / trạng thái / loại / ô Eisenhower) cho Danh sách + Ma trận; xoá 1 / nhiều task có xác nhận."""

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QMessageBox

from tests.qt_offscreen_app_helper import flush_qt_garbage, get_qapp

get_qapp()

from src.core.models import DatabaseManager  # noqa: E402
from src.ui.dashboard_tabs import dashboard_tasks_tab_widget as tab_module  # noqa: E402
from src.ui.dashboard_tabs import eisenhower_matrix_view_widget as matrix_module  # noqa: E402
from src.ui.dashboard_tabs import task_delete_confirmation as delete_module  # noqa: E402
from src.ui.dashboard_tabs.dashboard_tasks_tab_widget import DashboardTasksTabWidget  # noqa: E402
from src.ui.dashboard_tabs.task_filter_bar_widget import (  # noqa: E402
    UNSORTED,
    TaskFilterCriteria,
    fold_text,
    task_matches,
)


def _t(title, status="todo", category="deep_work", quadrant=None):
    return SimpleNamespace(title=title, status=status, category=category, quadrant=quadrant)


# ── task_matches (thuần) ────────────────────────────────────────────────────
def test_fold_text_ignores_case_and_vietnamese_accents():
    assert fold_text("Nộp THUẾ Đợt 2") == "nop thue dot 2"


def test_matches_text_status_category_quadrant():
    task = _t("Nộp thuế quý 3", category="shallow_work", quadrant=1)
    assert task_matches(task, TaskFilterCriteria(text="nop thue"))
    assert not task_matches(task, TaskFilterCriteria(text="email"))
    assert not task_matches(task, TaskFilterCriteria(status="done"))
    assert task_matches(task, TaskFilterCriteria(status="done"), ignore_status=True)
    assert task_matches(task, TaskFilterCriteria(category="shallow_work", quadrant=1))
    assert not task_matches(task, TaskFilterCriteria(category="deep_work"))
    assert not task_matches(task, TaskFilterCriteria(quadrant=UNSORTED))
    assert task_matches(_t("x"), TaskFilterCriteria(quadrant=UNSORTED))
    assert task_matches(_t("x", status="done"), TaskFilterCriteria(status="all"))
    assert not task_matches(_t("x", status="done"), TaskFilterCriteria())  # mặc định: chỉ việc đang mở


# ── tab Công việc ─────────────────────────────────────────────────────────
@pytest.fixture
def tab(memory_engine, monkeypatch):
    m = DatabaseManager.for_engine(memory_engine)
    for module in (tab_module, matrix_module, delete_module):
        monkeypatch.setattr(module, "db", m)
    widget = DashboardTasksTabWidget(focus_engine=SimpleNamespace())
    widget.mgr = m
    yield widget
    flush_qt_garbage()


def _list_titles(tab):
    return [tab.task_list.item(i).data(tab_module.Qt.ItemDataRole.UserRole + 1) for i in range(tab.task_list.count())]


def test_filter_applies_to_list_and_matrix(tab):
    m = tab.mgr
    m.add_task("Nộp thuế", quadrant=1)
    m.add_task("Gửi email", quadrant=2)
    done = m.add_task("Đã xong", quadrant=1)
    m.mark_task_done(done.id)
    tab.refresh()
    assert sorted(_list_titles(tab)) == ["Gửi email", "Nộp thuế"]  # mặc định ẩn việc đã xong

    tab.filter_bar.txt_search.setText("nop")
    assert _list_titles(tab) == ["Nộp thuế"]
    assert tab.matrix_view.cells[1].count() == 1 and tab.matrix_view.cells[2].count() == 0

    tab.filter_bar.txt_search.clear()
    tab.filter_bar.combo_status.setCurrentIndex(tab.filter_bar.combo_status.findData("done"))
    assert _list_titles(tab) == ["Đã xong"]

    tab.filter_bar.combo_status.setCurrentIndex(tab.filter_bar.combo_status.findData("open"))
    tab.filter_bar.combo_quadrant.setCurrentIndex(tab.filter_bar.combo_quadrant.findData(2))
    assert _list_titles(tab) == ["Gửi email"]


def test_show_list_clears_filter_hiding_the_requested_task(tab):
    hidden = tab.mgr.add_task("Ẩn bởi bộ lọc")
    tab.mgr.mark_task_done(hidden.id)
    tab.refresh()
    tab.show_list(hidden.id)
    assert tab.task_list.currentItem().data(tab_module.Qt.ItemDataRole.UserRole) == hidden.id


def test_bulk_delete_selected_asks_once_then_deletes_all(tab, monkeypatch):
    a, b, keep = (tab.mgr.add_task(t) for t in ("A", "B", "Giữ"))
    tab.refresh()
    asked = []
    monkeypatch.setattr(delete_module.QMessageBox, "question",
                        lambda *args, **k: asked.append(args[2]) or QMessageBox.StandardButton.Yes)
    for i in range(tab.task_list.count()):
        item = tab.task_list.item(i)
        item.setSelected(item.data(tab_module.Qt.ItemDataRole.UserRole) in (a.id, b.id))
    assert "(2)" in tab.btn_delete.text()

    tab.btn_delete.click()
    assert len(asked) == 1 and "2" in asked[0]
    assert [t.id for t in tab.mgr.list_tasks()] == [keep.id]


def test_delete_cancelled_keeps_tasks(tab, monkeypatch):
    task = tab.mgr.add_task("Không xoá")
    tab.refresh()
    monkeypatch.setattr(delete_module.QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    tab.task_list.item(0).setSelected(True)
    tab.btn_delete.click()
    assert [t.id for t in tab.mgr.list_tasks()] == [task.id]


def test_delete_tasks_db_skips_unknown_and_duplicates(memory_engine):
    m = DatabaseManager.for_engine(memory_engine)
    a, b = m.add_task("A"), m.add_task("B")
    assert m.delete_tasks([a.id, a.id, "khong-co"]) == 1
    assert [t.id for t in m.list_tasks()] == [b.id]
