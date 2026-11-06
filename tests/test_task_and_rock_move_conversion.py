"""Kiểm thử tính năng chuyển đổi qua lại giữa TODO Task và Rocks:
- db.move_task_to_rock và db.move_rock_to_task
- DashboardTasksTabWidget nút và context menu Chuyển sang Rocks
- EisenhowerMatrixViewWidget context menu Chuyển sang Rocks
- TaskDetailEditDialog nút Chuyển sang Rocks
- WorkRocksAndCalendarTab nút và context menu Chuyển sang Todo
- Round-trip Task <-> Rock bảo toàn tiêu đề và ghi chú.
"""

from types import SimpleNamespace
from PySide6.QtCore import Qt

from tests.qt_offscreen_app_helper import get_qapp
from src.core.models import DatabaseManager, db
from src.engines.work.rock_model_and_repository import RockRepository


def test_db_move_task_to_rock_and_back_roundtrip(memory_engine):
    mgr = DatabaseManager.for_engine(memory_engine)
    rock_repo = RockRepository(memory_engine)

    # 1. Tạo task ban đầu
    task = mgr.add_task("Dự án nâng cấp hệ thống", category="deep_work", estimated_pomodoros=3)
    mgr.append_task_notes(task.id, "Cần xin cấp quyền truy cập server và DB")

    # 2. Chuyển Task sang Rock
    rock = mgr.move_task_to_rock(task.id)
    assert rock is not None
    assert rock.title == "Dự án nâng cấp hệ thống"
    assert "Cần xin cấp quyền truy cập server và DB" in rock.detail
    assert rock.status == "open"

    # Task không còn trong danh sách Task
    assert mgr.get_task(task.id) is None
    # Rock đã có trong danh sách Rock
    assert rock_repo.get(rock.id) is not None

    # 3. Chuyển Rock ngược lại sang Todo Task
    restored_task = mgr.move_rock_to_task(rock.id)
    assert restored_task is not None
    assert restored_task.title == "Dự án nâng cấp hệ thống"
    assert "Cần xin cấp quyền truy cập server và DB" in restored_task.notes
    assert restored_task.category == "deep_work"
    assert restored_task.status == "todo"

    # Rock không còn trong danh sách Rock
    assert rock_repo.get(rock.id) is None
    # Task đã xuất hiện trong danh sách Task
    assert mgr.get_task(restored_task.id) is not None


def test_db_move_invalid_ids_returns_none(memory_engine):
    mgr = DatabaseManager.for_engine(memory_engine)
    assert mgr.move_task_to_rock("non-existent-id") is None
    assert mgr.move_rock_to_task("non-existent-id") is None


def test_tasks_tab_button_moves_selected_task_to_rock():
    from src.ui.dashboard_tabs.dashboard_tasks_tab_widget import DashboardTasksTabWidget
    get_qapp()

    task = db.add_task("Nhiệm vụ khó cần đẩy sang Rock")
    focus = SimpleNamespace()
    tab = DashboardTasksTabWidget(focus_engine=focus)
    tab.refresh()

    changed = []
    tab.data_changed.connect(lambda: changed.append(1))

    # Chọn task trong danh sách
    item = tab._select_task(task.id)
    assert item is not None
    assert item.isSelected()

    # Nhấn nút Chuyển sang Rocks
    tab.btn_move_to_rock.click()

    # Task bị xoá khỏi danh sách Tasks
    assert db.get_task(task.id) is None
    assert changed == [1]

    # Rock được tạo trong RockRepository
    rock_repo = RockRepository(db.engine)
    rocks = rock_repo.list()
    matching = [r for r in rocks if r.title == "Nhiệm vụ khó cần đẩy sang Rock"]
    assert len(matching) == 1

    # Cleanup rock
    rock_repo.delete(matching[0].id)


def test_matrix_context_menu_has_move_to_rock_action():
    from src.ui.dashboard_tabs.eisenhower_matrix_view_widget import EisenhowerMatrixViewWidget
    get_qapp()

    task = db.add_task("Task ma trận", quadrant=1)
    matrix = EisenhowerMatrixViewWidget()
    matrix.refresh()

    menu = matrix.build_context_menu(task.id)
    actions = [a.text() for a in menu.actions()]
    assert any("Rocks" in text for text in actions)

    # Thử gọi move_to_rock
    matrix.move_to_rock(task.id)
    assert db.get_task(task.id) is None

    rock_repo = RockRepository(db.engine)
    matching = [r for r in rock_repo.list() if r.title == "Task ma trận"]
    assert len(matching) == 1
    rock_repo.delete(matching[0].id)


def test_task_detail_dialog_move_to_rock():
    from src.ui.task_detail_edit_dialog import TaskDetailEditDialog
    get_qapp()

    task = db.add_task("Task xem chi tiết", notes="Ghi chú quan trọng")
    focus = SimpleNamespace(active_task_id=task.id)
    dialog = TaskDetailEditDialog(task.id, focus_engine=focus)

    assert not dialog.btn_move_to_rock.isHidden()
    saved = []
    dialog.task_saved.connect(saved.append)

    # Click chuyển sang Rock
    dialog.btn_move_to_rock.click()

    # Task đã chuyển sang Rock và active_task_id được xoá
    assert db.get_task(task.id) is None
    assert focus.active_task_id is None
    assert saved == [task.id]

    rock_repo = RockRepository(db.engine)
    matching = [r for r in rock_repo.list() if r.title == "Task xem chi tiết"]
    assert len(matching) == 1
    assert "Ghi chú quan trọng" in matching[0].detail
    rock_repo.delete(matching[0].id)


def test_work_tab_move_rock_to_todo_button_and_context_menu():
    from src.ui.module_tabs.work_rocks_and_calendar_tab_widget import WorkRocksAndCalendarTab
    get_qapp()

    rock_repo = RockRepository(db.engine)
    rock = rock_repo.add("Vướng mắc tồn đọng cần xử lý", "Cần gọi đối tác xác nhận")

    class DummyEngine:
        def __init__(self):
            self.rocks = rock_repo
            self.today_rows = lambda: []
            self.calendar_status_text = lambda: "Lịch trống"
        def move_rock_to_task(self, rock_id):
            return db.move_rock_to_task(rock_id)

    tab = WorkRocksAndCalendarTab(DummyEngine())
    assert tab.rock_list.count() >= 1

    # Tìm dòng chứa rock
    found_row = None
    for row in range(tab.rock_list.count()):
        if tab.rock_list.item(row).data(Qt.ItemDataRole.UserRole) == rock.id:
            found_row = row
            break
    assert found_row is not None

    tab.rock_list.setCurrentRow(found_row)
    # Nhấn nút chuyển sang Todo
    tab.btn_move_to_todo.click()

    # Rock đã bị xoá
    assert rock_repo.get(rock.id) is None
    # Task đã được tạo trong db
    matching_tasks = [t for t in db.list_tasks(include_done=False) if t.title == "Vướng mắc tồn đọng cần xử lý"]
    assert len(matching_tasks) == 1
    assert "Cần gọi đối tác xác nhận" in matching_tasks[0].notes

    # Cleanup task
    db.delete_task(matching_tasks[0].id)
