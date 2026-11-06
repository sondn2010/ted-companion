"""Link tên task trong bong bóng (nhắc việc lúc bắt đầu Deep Work) → popup Chi tiết công việc; popup sửa được task;
tab Công việc mở popup sửa (nút ✏️ / double-click / chuột phải ở Ma trận)."""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt

from tests.qt_offscreen_app_helper import get_qapp

from src.core.models import DatabaseManager, db
from src.engines.work.deep_work_next_task_announcer import compose_next_task_message, next_task_links
from src.ui.bubble_task_link_html import linkify_task_titles, task_id_from_href


def _t(tid, title, quadrant=1):
    return SimpleNamespace(id=tid, title=title, quadrant=quadrant)


# ── linkify ────────────────────────────────────────────────────────────────
def test_linkify_wraps_title_and_escapes_rest():
    html = linkify_task_titles("Gợi ý: Q1 còn <Nộp thuế>, làm\nngay", [("<Nộp thuế>", "id-1"), ("Không có", "id-2")])
    assert "href='task:id-1'" in html and "&lt;Nộp thuế&gt;</a>" in html
    assert "id-2" not in html and "<br>" in html


def test_linkify_longer_title_wins_over_contained_one():
    html = linkify_task_titles("Anh đang làm Viết spec API", [("Viết spec", "a"), ("Viết spec API", "b")])
    assert html.count("<a ") == 1 and "task:b" in html


def test_task_id_from_href():
    assert task_id_from_href("task:abc") == "abc"
    assert task_id_from_href("https://x") is None and task_id_from_href("task:") is None


def test_next_task_links_match_message_titles():
    ranked = [_t("a", "Viết spec"), _t("b", "Review PR", 2)]
    msg = compose_next_task_message("a", "Viết spec", ranked)
    html = linkify_task_titles(msg, next_task_links("a", "Viết spec", ranked))
    assert "task:a" in html and "task:b" in html


# ── DB update_task ────────────────────────────────────────────────────────
def test_update_task_edits_fields_and_moves_to_end_of_new_quadrant(memory_engine):
    m = DatabaseManager.for_engine(memory_engine)
    m.set_task_quadrant(m.add_task("Có sẵn ở Q2").id, 2, order=5)
    task = m.add_task("Cũ", quadrant=1)
    updated = m.update_task(task.id, title="  Mới  ", category="shallow_work", estimated_pomodoros=3,
                            quadrant=2, status="in_progress", scheduled_date="2026-10-22")
    assert (updated.title, updated.category, updated.estimated_pomodoros) == ("Mới", "shallow_work", 3)
    assert (updated.quadrant, updated.status, updated.scheduled_date) == (2, "in_progress", "2026-10-22")
    assert updated.matrix_order == 6.0 and updated.synced_to_hermes is False


def test_update_task_rejects_empty_title_and_unknown_id(memory_engine):
    m = DatabaseManager.for_engine(memory_engine)
    task = m.add_task("A")
    with pytest.raises(ValueError):
        m.update_task(task.id, "  ", "deep_work", 1, None, "todo", "2026-10-21")
    assert m.update_task("nope", "B", "deep_work", 1, None, "todo", "2026-10-21") is None


# ── popup sửa task ───────────────────────────────────────────────────────
def test_dialog_saves_changes_and_syncs_running_session_title():
    from src.ui.task_detail_edit_dialog import TaskDetailEditDialog

    get_qapp()
    task = db.add_task("Viết báo cáo", quadrant=2)
    focus = SimpleNamespace(active_task_id=task.id, active_task_title="Viết báo cáo")
    dialog = TaskDetailEditDialog(task.id, focus_engine=focus)
    saved = []
    dialog.task_saved.connect(saved.append)

    dialog.txt_title.setText("Viết báo cáo quý 3")
    dialog.combo_quadrant.setCurrentIndex(dialog.combo_quadrant.findData(1))
    dialog.spin_pomodoros.setValue(4)
    dialog.btn_save.click()

    stored = db.get_task(task.id)
    assert (stored.title, stored.quadrant, stored.estimated_pomodoros) == ("Viết báo cáo quý 3", 1, 4)
    assert saved == [task.id] and focus.active_task_title == "Viết báo cáo quý 3"


def test_dialog_empty_title_shows_error_and_does_not_save():
    from src.ui.task_detail_edit_dialog import TaskDetailEditDialog

    get_qapp()
    task = db.add_task("Giữ nguyên")
    dialog = TaskDetailEditDialog(task.id)
    dialog.txt_title.setText("   ")
    dialog.btn_save.click()
    assert db.get_task(task.id).title == "Giữ nguyên" and not dialog.lbl_error.isHidden()


def test_dialog_for_deleted_task_shows_not_found():
    from src.ui.task_detail_edit_dialog import TaskDetailEditDialog

    get_qapp()
    dialog = TaskDetailEditDialog("khong-ton-tai", dashboard=SimpleNamespace())
    assert dialog.btn_save.isHidden() and dialog.btn_open_list.isHidden()


# ── bong bóng ─────────────────────────────────────────────────────────────
def test_bubble_link_opens_task_detail_and_plain_messages_stay_plain():
    from src.ui.pet_speech_bubble_widget import PetSpeechBubble

    get_qapp()
    task = db.add_task("Nộp thuế", quadrant=1)
    bubble = PetSpeechBubble()
    bubble.show_message("Gợi ý: Q1 còn Nộp thuế, anh cân nhắc nhé.", timeout_ms=0, task_links=[("Nộp thuế", task.id)])
    assert bubble._label.textFormat() == Qt.TextFormat.RichText and f"task:{task.id}" in bubble._label.text()
    assert bubble.current_text() == "Gợi ý: Q1 còn Nộp thuế, anh cân nhắc nhé."

    bubble._label.linkActivated.emit(f"task:{task.id}")
    assert bubble._task_dialog is not None and bubble._task_dialog.task_id == task.id

    bubble.show_message("<b>không phải HTML</b>", timeout_ms=0)
    assert bubble._label.textFormat() == Qt.TextFormat.PlainText and bubble._label.text() == "<b>không phải HTML</b>"


# ── tab Công việc ─────────────────────────────────────────────────────────
def test_tasks_tab_edit_entry_points():
    from src.ui.dashboard_tabs.dashboard_tasks_tab_widget import DashboardTasksTabWidget

    get_qapp()
    task = db.add_task("Sửa từ tab")
    tab = DashboardTasksTabWidget(focus_engine=SimpleNamespace())
    tab.refresh()
    changed = []
    tab.data_changed.connect(lambda: changed.append(1))

    menu_texts = [a.text() for a in tab.matrix_view.build_context_menu(task.id).actions()]
    assert any("✏️" in t for t in menu_texts)

    dialog = tab.open_task_editor(task.id)
    dialog.txt_title.setText("Đã sửa từ tab")
    dialog.btn_save.click()
    assert db.get_task(task.id).title == "Đã sửa từ tab" and changed == [1]
