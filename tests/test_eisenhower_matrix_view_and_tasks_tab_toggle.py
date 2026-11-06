"""Ma trận Eisenhower: refresh đặt task đúng ô/thứ tự, drop-persist, menu chuột phải, toggle List|Matrix."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests.qt_offscreen_app_helper import flush_qt_garbage, get_qapp

get_qapp()

from src.core.models import DatabaseManager  # noqa: E402
from src.ui.dashboard_tabs import dashboard_tasks_tab_widget as tab_module  # noqa: E402
from src.ui.dashboard_tabs import eisenhower_matrix_view_widget as matrix_module  # noqa: E402
from src.ui.dashboard_tabs import task_delete_confirmation as delete_module  # noqa: E402
from src.ui.dashboard_tabs.dashboard_tasks_tab_widget import DashboardTasksTabWidget  # noqa: E402
from src.ui.dashboard_tabs.eisenhower_matrix_view_widget import EisenhowerMatrixViewWidget  # noqa: E402


@pytest.fixture
def mgr(memory_engine, monkeypatch):
    m = DatabaseManager.__new__(DatabaseManager)  # DB RAM riêng, không đụng DB thật
    m.engine = memory_engine
    monkeypatch.setattr(matrix_module, "db", m)
    monkeypatch.setattr(tab_module, "db", m)
    monkeypatch.setattr(delete_module, "db", m)
    yield m
    flush_qt_garbage()


def _ids(view, q):
    return view.cells[q].task_ids()


def test_refresh_places_open_tasks_in_cells_in_order(mgr):
    a = mgr.add_task("A", quadrant=1)
    b = mgr.add_task("B", quadrant=1)
    c = mgr.add_task("C", category="parked_idea")  # chưa phân loại
    d = mgr.add_task("D", quadrant=4)
    done = mgr.add_task("Xong", quadrant=2)
    mgr.mark_task_done(done.id)
    mgr.reorder_quadrant(1, [b.id, a.id])

    view = EisenhowerMatrixViewWidget()
    view.refresh()

    assert _ids(view, 1) == [b.id, a.id]
    assert _ids(view, None) == [c.id]
    assert _ids(view, 4) == [d.id]
    assert _ids(view, 2) == []  # task done bị ẩn
    assert view.cells[None].item(0).text().startswith("🅿️")
    assert view.watermarks[1].title.endswith("· 2")  # chữ chìm "LÀM NGAY · 2"


def test_apply_drop_between_cells_persists_both_columns(mgr):
    a, b, c = (mgr.add_task(t, quadrant=3) for t in "ABC")
    x = mgr.add_task("X", quadrant=1)
    mgr.reorder_quadrant(3, [a.id, b.id, c.id])
    view = EisenhowerMatrixViewWidget()
    view.refresh()
    changed = MagicMock()
    view.data_changed.connect(changed)

    view.apply_drop(b.id, 1, [x.id, b.id])  # Q3 -> Q1, chèn sau X

    assert _ids(view, 1) == [x.id, b.id]
    assert _ids(view, 3) == [a.id, c.id]
    tasks = {t.id: t for t in mgr.list_tasks()}
    assert (tasks[b.id].quadrant, tasks[b.id].matrix_order) == (1, 1.0)
    assert (tasks[a.id].matrix_order, tasks[c.id].matrix_order) == (0.0, 1.0)  # cột nguồn đánh số lại
    changed.assert_called_once()


def test_apply_drop_reorder_within_cell_and_to_unsorted(mgr):
    a, b = mgr.add_task("A", quadrant=2), mgr.add_task("B", quadrant=2)
    mgr.reorder_quadrant(2, [a.id, b.id])
    view = EisenhowerMatrixViewWidget()
    view.refresh()

    view.apply_drop(b.id, 2, [b.id, a.id])
    assert _ids(view, 2) == [b.id, a.id]

    view.apply_drop(a.id, None, [a.id])
    assert _ids(view, None) == [a.id] and _ids(view, 2) == [b.id]
    assert {t.id: t.quadrant for t in mgr.list_tasks()}[a.id] is None


def test_context_menu_move_done_delete(mgr, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    asked = []
    monkeypatch.setattr(delete_module.QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.Yes)
    t = mgr.add_task("T", quadrant=None)
    keep = mgr.add_task("K", quadrant=1)
    view = EisenhowerMatrixViewWidget()
    view.refresh()

    menu = view.build_context_menu(t.id)
    menu.actions()  # tạo menu thật
    move_q2 = next(a for a in menu.actions() if a.text().startswith("Chuyển tới Q2"))
    move_q2.trigger()
    assert _ids(view, 2) == [t.id] and _ids(view, None) == []

    next(a for a in view.build_context_menu(t.id).actions() if "Hoàn thành" in a.text()).trigger()
    assert _ids(view, 2) == []
    assert {x.id: x.status for x in mgr.list_tasks()}[t.id] == "done"

    next(a for a in view.build_context_menu(keep.id).actions() if "Xoá" in a.text()).trigger()
    assert _ids(view, 1) == []
    assert all(x.id != keep.id for x in mgr.list_tasks())
    assert len(asked) == 1 and "K" in asked[0]  # xoá luôn hỏi xác nhận, có tên task


def test_double_click_item_requests_pomodoro(mgr):
    t = mgr.add_task("Việc", quadrant=1)
    view = EisenhowerMatrixViewWidget()
    view.refresh()
    got = MagicMock()
    view.task_activated.connect(got)
    view.cells[1].itemDoubleClicked.emit(view.cells[1].item(0))
    got.assert_called_once_with(t.id, "Việc")


def test_tab_toggle_defaults_to_matrix_persists_and_starts_pomodoro(mgr, monkeypatch):
    extra = {}
    save = MagicMock()
    monkeypatch.setattr(tab_module.settings, "_extra", extra)
    monkeypatch.setattr(tab_module.settings, "save", save)
    focus = SimpleNamespace(tasks_updated=MagicMock(connect=MagicMock()), start_focus_session=MagicMock())
    t = mgr.add_task("Làm", quadrant=1)

    tab = DashboardTasksTabWidget(focus)
    assert tab.current_view() == "matrix"  # mặc định
    tab.refresh()
    assert _ids(tab.matrix_view, 1) == [t.id] and tab.task_list.count() == 1

    tab.btn_view_list.click()
    assert tab.current_view() == "list" and extra["tasks_view"] == "list"
    save.assert_called()

    assert DashboardTasksTabWidget(focus).current_view() == "list"  # nhớ lựa chọn

    tab.matrix_view.cells[1].itemDoubleClicked.emit(tab.matrix_view.cells[1].item(0))
    assert focus.start_focus_session.call_args.kwargs["task_id"] == t.id


def test_tab_toggle_survives_save_failure_and_bad_stored_value(mgr, monkeypatch):
    monkeypatch.setattr(tab_module.settings, "_extra", {"tasks_view": "rác"})
    monkeypatch.setattr(tab_module.settings, "save", MagicMock(side_effect=OSError("disk")))
    tab = DashboardTasksTabWidget(SimpleNamespace(tasks_updated=MagicMock(connect=MagicMock())))
    assert tab.current_view() == "matrix"
    tab.btn_view_list.click()  # lỗi lưu chỉ log, không văng
    assert tab.current_view() == "list"


def test_delete_all_q4_tasks_confirmed(mgr, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    q4_a = mgr.add_task("Q4 A", quadrant=4)
    q4_b = mgr.add_task("Q4 B", quadrant=4)
    q1_keep = mgr.add_task("Q1 Keep", quadrant=1)

    view = EisenhowerMatrixViewWidget()
    view.refresh()
    assert len(_ids(view, 4)) == 2

    asked = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: asked.append(args[2]) or QMessageBox.StandardButton.Yes,
    )

    view.delete_all_q4_tasks()

    assert _ids(view, 4) == []
    assert _ids(view, 1) == [q1_keep.id]
    tasks = {t.id: t for t in mgr.list_tasks()}
    assert q4_a.id not in tasks
    assert q4_b.id not in tasks
    assert q1_keep.id in tasks
    assert len(asked) == 1 and "2" in asked[0]


def test_delete_all_q4_tasks_cancelled(mgr, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    q4_task = mgr.add_task("Q4 Never Delete", quadrant=4)

    view = EisenhowerMatrixViewWidget()
    view.refresh()

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )

    view.delete_all_q4_tasks()

    assert _ids(view, 4) == [q4_task.id]
    assert any(t.id == q4_task.id for t in mgr.list_tasks())


def test_delete_all_q4_tasks_empty_shows_info(mgr, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    info_called = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: info_called.append(args[2]),
    )

    view = EisenhowerMatrixViewWidget()
    view.refresh()

    view.delete_all_q4_tasks()

    assert len(info_called) == 1


def test_task_table_widget_columns_and_content(mgr):
    task = mgr.add_task(
        "Nhiệm vụ kiểm thử đa cột",
        category="deep_work",
        estimated_pomodoros=5,
        quadrant=2,
        notes="Ghi chú chi tiết cho kiểm thử bảng danh sách",
    )
    mgr.update_task(
        task_id=task.id,
        title="Nhiệm vụ kiểm thử đa cột",
        category="deep_work",
        estimated_pomodoros=5,
        quadrant=2,
        status="todo",
        scheduled_date="2026-10-30",
        notes="Ghi chú chi tiết cho kiểm thử bảng danh sách",
    )
    mgr.increment_task_pomodoro(task.id)
    mgr.increment_task_pomodoro(task.id)

    tab = DashboardTasksTabWidget(SimpleNamespace(tasks_updated=MagicMock(connect=MagicMock())))
    tab.refresh()

    assert tab.task_list.count() == 1
    assert tab.task_list.columnCount() == 7

    # Check horizontal headers
    headers = [tab.task_list.horizontalHeaderItem(c).text() for c in range(7)]
    assert "Trạng thái" in headers[0] or "Status" in headers[0]
    assert "Tên công việc" in headers[1] or "Title" in headers[1]
    assert "Ma trận" in headers[2] or "Matrix" in headers[2]
    assert "Phân loại" in headers[3] or "Category" in headers[3]
    assert "Pomodoro" in headers[4]
    assert "Ngày" in headers[5] or "Due" in headers[5] or "Date" in headers[5]
    assert "Ghi chú" in headers[6] or "Notes" in headers[6]

    # Check row 0 cell contents
    item_status = tab.task_list.item(0, 0)
    item_title = tab.task_list.item(0, 1)
    item_matrix = tab.task_list.item(0, 2)
    item_cat = tab.task_list.item(0, 3)
    item_pomo = tab.task_list.item(0, 4)
    item_date = tab.task_list.item(0, 5)
    item_notes = tab.task_list.item(0, 6)

    assert "Chưa làm" in item_status.text() or "To do" in item_status.text()
    assert item_title.text() == "Nhiệm vụ kiểm thử đa cột"
    assert "Q2" in item_matrix.text()
    assert "Deep Work" in item_cat.text()
    assert "🍅 2/5" in item_pomo.text()
    assert "2026-10-30" in item_date.text()
    assert "Ghi chú chi tiết" in item_notes.text()
    assert item_notes.toolTip() == "Ghi chú chi tiết cho kiểm thử bảng danh sách"
    assert item_status.data(tab_module.Qt.ItemDataRole.UserRole) == task.id
    assert item_title.data(tab_module.Qt.ItemDataRole.UserRole + 1) == "Nhiệm vụ kiểm thử đa cột"
