"""Nút "🅿️ Xem Bãi đỗ" trên bong bóng sau khi đỗ ý tưởng + menu work "Danh sách công việc" → tab Công việc dạng Danh sách."""

from types import SimpleNamespace

from PySide6.QtCore import Qt

from tests.qt_offscreen_app_helper import get_qapp

from src.core.focus_engine import FocusEngine
from src.core.i18n import tr
from src.core.models import db
from src.engines.work.work_module_engine import WorkModuleEngine
from src.modules_runtime.module_manifest_schema import ModuleManifest
from src.ui.button_text_escape import btn_text
from src.ui.dashboard_window import DashboardWindow
from src.ui.pet_speech_bubble_widget import PetSpeechBubble

WORK = ModuleManifest(id="work", name="Công việc", icon="💼", engine="work", connection="work", enabled=True)


def _dashboard(focus):
    registry = SimpleNamespace(
        modules_changed=SimpleNamespace(connect=lambda _slot: None),
        enabled=lambda: [], active=lambda: None, all=lambda: [], errors={},
    )
    return DashboardWindow(focus, registry)


def test_park_in_bubble_shows_button_that_opens_tasks_list_with_idea_selected():
    get_qapp()
    focus = FocusEngine(audio_manager=None)
    dash = _dashboard(focus)
    dash.tasks_tab._set_view("matrix", persist=False)
    bubble = PetSpeechBubble(focus_engine=focus, dashboard=dash)
    bubble._input_field.setText("Ý tưởng đỗ để test nút")
    bubble._on_park_submit()

    assert bubble._buttons.count() == 1
    btn = bubble._buttons.itemAt(0).widget()
    assert btn.text() == btn_text(tr("bubble_btn_view_parking"))
    btn.click()

    tab = dash.tasks_tab
    assert dash.tabs.currentWidget() is tab and tab.current_view() == "list"
    selected = tab.task_list.currentItem()
    parked = next(t for t in db.list_tasks() if t.title == "Ý tưởng đỗ để test nút")
    assert selected is not None and selected.data(Qt.ItemDataRole.UserRole) == parked.id
    assert not bubble.isVisible()


def test_bubble_without_dashboard_parks_without_button():
    get_qapp()
    bubble = PetSpeechBubble(focus_engine=FocusEngine(audio_manager=None))
    bubble._input_field.setText("Ý tưởng không có dashboard")
    bubble._on_park_submit()
    assert bubble._buttons.count() == 0


def test_work_menu_tasks_action_opens_tasks_list():
    get_qapp()
    opened = []
    ctx = SimpleNamespace(dashboard=SimpleNamespace(open_tasks_list=lambda task_id=None: opened.append(task_id)),
                          kv=None, client_pool=None, focus_engine=None, bubble=None)
    engine = WorkModuleEngine(WORK, ctx, db_engine=db.engine)
    engine.handle_action("tasks")
    assert opened == [None]


def test_plus_button_popup_adds_through_focus_engine_so_task_gets_classified():
    get_qapp()
    focus = FocusEngine(audio_manager=None)
    added = []
    focus.task_added.connect(lambda tid, title: added.append(title))
    tab = _dashboard(focus).tasks_tab
    dialog = tab.open_task_creator()
    dialog.txt_title.setText("Viết đề xuất dự án")
    dialog.combo_quadrant.setCurrentIndex(dialog.combo_quadrant.findData(2))
    dialog.btn_save.click()
    assert added == ["Viết đề xuất dự án"]
    created = next(t for t in db.list_tasks() if t.title == "Viết đề xuất dự án")
    assert created.quadrant == 2 and created.status == "todo"


def test_plus_popup_with_empty_title_shows_error_and_adds_nothing():
    get_qapp()
    focus = FocusEngine(audio_manager=None)
    added = []
    focus.task_added.connect(lambda tid, title: added.append(tid))
    tab = _dashboard(focus).tasks_tab
    dialog = tab.open_task_creator()
    dialog.btn_save.click()
    assert added == [] and not dialog.lbl_error.isHidden()


def test_mcp_created_task_is_also_classified(tmp_path, monkeypatch):
    import json
    from src.config import settings

    get_qapp()
    cmd_file = tmp_path / "queue.json"
    cmd_file.write_text(json.dumps([{"type": "refresh_tasks", "task_id": "t-1", "title": "Từ Hermes"}]), encoding="utf-8")
    monkeypatch.setattr(settings, "ipc_command_file", cmd_file)
    focus = FocusEngine(audio_manager=None)
    added = []
    focus.task_added.connect(lambda tid, title: added.append((tid, title)))
    focus._poll_mcp_commands()
    assert added == [("t-1", "Từ Hermes")]
