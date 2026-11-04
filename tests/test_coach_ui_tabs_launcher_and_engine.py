"""Tab Hôm nay/Tiến độ với đủ 5 kind, launcher theo kind, menu engine, dialog viết bài (offline → Chấm lại)."""

import asyncio
import json

import httpx
from coach_test_support import MODULE, quiz
from coach_ui_test_support import LOCAL_NOW, hermes_client, make_services, save_plan
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton
from qt_offscreen_app_helper import get_qapp
from shiboken6 import delete, isValid

from src.core.background_task_spawner import _running_tasks
from src.engines.coach.agenda_kind_launcher import KIND_RENDERERS, AgendaKindLauncher
from src.engines.coach.coach_module_engine import CoachModuleEngine
from src.engines.coach.coach_review_session_builder import build_session_items, quiz_limit_for_agenda
from src.modules_runtime.engine_fixed_menus import ENGINE_MENUS
from src.ui.module_tabs.coach_module_tab_widget import CoachModuleTabWidget
from src.ui.module_tabs.coach_today_tab_widget import countdown_text
from src.ui.quiz.writing_submit_dialog import WritingSubmitDialog

FIVE_KINDS = [
    {"id": "a-quiz", "kind": "quiz", "title": "Ôn thì", "minutes": 10, "topic": "english.tenses"},
    {"id": "a-step", "kind": "step", "title": "Giải PT", "topic": "math.eq"},
    {"id": "a-write", "kind": "writing", "title": "Viết đoạn", "prompt": "Tả gia đình", "topic": "hsk.w"},
    {"id": "a-chat", "kind": "chat", "title": "Luyện nói", "prompt": "Hỏi mình về sở thích"},
    {"id": "a-task", "kind": "task", "title": "Chép từ mới", "when": "20:00"},
]
PLAN = dict(
    display={"title": "Lớp 8", "phase": "Nền tảng", "countdown": {"label": "thi vào 10", "date": "2028-06-01"}},
    agenda=FIVE_KINDS,
    milestones=[{"id": "m1", "title": "Thi HSK3", "due_date": "2026-10-10"}, {"id": "m2", "title": "Thi thử", "due_date": "2026-12-01"}],
    checklist=[{"id": "c1", "title": "Học 50 từ"}, {"id": "c2", "title": "Nộp hồ sơ", "status": "done"}],
    policy={"review_interval_mins": 20, "daily_cap": 15, "new_per_day": 8, "leitner_days": [0.007, 1, 3, 7, 14, 30],
            "rationale": "Ôn nhẹ buổi tối"},
)


def _tab(engine, **plan):
    get_qapp()
    services, ctx = make_services(engine)
    save_plan(services, **(plan or PLAN))
    launcher = AgendaKindLauncher(services)
    return CoachModuleTabWidget(services, launcher), services, ctx, launcher


def _texts(widget, kind=QLabel):
    return [w.text() for w in widget.findChildren(kind)]


async def _drain():
    await asyncio.gather(*list(_running_tasks))


def test_kind_registry_covers_all_five_kinds():
    assert set(KIND_RENDERERS) == {"quiz", "step", "writing", "chat", "task"}


def test_menu_actions_match_engine_fixed_menu(memory_engine):
    get_qapp()
    services, ctx = make_services(memory_engine)
    engine = CoachModuleEngine(services.manifest, ctx, services=services)
    assert set(engine._actions) == {a.id for a in ENGINE_MENUS["coach"]}


def test_today_tab_renders_header_all_five_agenda_kinds_policy_and_sync(memory_engine):
    tab, services, _ctx, _l = _tab(memory_engine)
    texts = _texts(tab.today)
    assert "Lớp 8 · Nền tảng" in texts
    assert any(t.startswith("Còn ") and "thi vào 10" in t for t in texts)
    joined = "\n".join(texts + _texts(tab.today, QCheckBox))
    for title in ("Ôn thì", "Giải PT", "Viết đoạn", "Luyện nói", "Chép từ mới"):
        assert title in joined
    assert "🧠 Ôn thì · 10'" in joined and "☑️ Chép từ mới · 20:00" in joined
    assert [b.text() for b in tab.today.findChildren(QPushButton)].count("Bắt đầu") == 4   # task = checkbox
    assert "Ôn mỗi 20 phút · tối đa 15 câu/ngày · 8 câu mới/ngày" in texts
    assert "Ôn nhẹ buổi tối" in texts
    assert tab.today.sync_label.text().startswith("Đồng bộ lần cuối: ")


def test_today_tab_without_snapshot_says_not_synced(memory_engine):
    get_qapp()
    services, _ = make_services(memory_engine)
    tab = CoachModuleTabWidget(services, AgendaKindLauncher(services))
    assert tab.today.sync_label.text() == "Chưa đồng bộ"
    assert tab.today.title_label.text() == "THCS"


def test_countdown_text_edge_cases():
    from datetime import date
    assert countdown_text({"label": "X", "date": "2026-10-22"}, date(2026, 10, 19)) == "Còn 3 ngày tới X"
    assert countdown_text({"label": "X"}, date(2026, 10, 19)) == ""


def test_task_checkbox_marks_done_and_row_shows_tick(memory_engine):
    tab, services, _ctx, _l = _tab(memory_engine)
    services.on_changed = tab.refresh
    box = next(b for b in tab.today.findChildren(QCheckBox) if "Chép từ mới" in b.text())
    box.setChecked(True)
    assert "a-task" in services.plans.done_ids(MODULE)
    assert any("Chép từ mới" in b.text() and "✓" in b.text() and not b.isEnabled() for b in tab.today.findChildren(QCheckBox))


def test_progress_section_milestones_overdue_checklist_stats_flag_and_history(memory_engine):
    tab, services, _ctx, _l = _tab(memory_engine)
    services.items.insert_items_dedup(MODULE, [quiz("Q1", topic="english.t"), quiz("Q2", topic="math.e")], LOCAL_NOW)
    first = services.items.first_unseen(MODULE, "english.t", None)
    services.attempts.record_answer(MODULE, first.id, "x", True, 5, LOCAL_NOW, [0.007, 1, 3, 7, 14, 30])
    services.items.flag_item(first.id, "đề lỗi")
    services.plans.add_writing_submission(MODULE, "Đề chưa chấm", "bài", LOCAL_NOW)
    tab.progress.refresh()
    labels = _texts(tab.progress)
    assert labels.index(next(t for t in labels if "Thi HSK3" in t)) < labels.index(next(t for t in labels if "Thi thử" in t))
    overdue = next(w for w in tab.progress.findChildren(QLabel) if "Thi HSK3" in w.text())
    assert "quá hạn 9 ngày" in overdue.text() and overdue.objectName() == "ErrorLabel"
    boxes = {b.text().split(" [")[0].split(" ·")[0]: b for b in tab.progress.findChildren(QCheckBox)}
    assert boxes["Học 50 từ"].isEnabled() and not boxes["Nộp hồ sơ"].isEnabled() and boxes["Nộp hồ sơ"].isChecked()
    assert "english: 1/1 đúng (100%)" in labels
    assert any("đề lỗi" in t for t in labels)
    buttons = [b.text() for b in tab.progress.findChildren(QPushButton)]
    assert "Bỏ cờ" in buttons and "Chấm lại" in buttons
    next(b for b in tab.progress.findChildren(QPushButton) if b.text() == "Bỏ cờ").click()
    assert services.items.flagged_items(MODULE) == []
    next(b for b in tab.progress.findChildren(QCheckBox) if b.text().startswith("Học 50")).setChecked(True)
    assert "c1" in services.plans.done_ids(MODULE)


def test_chat_kind_opens_quick_chat_with_prompt_and_marks_done(memory_engine):
    _tab_, services, ctx, launcher = _tab(memory_engine)
    launcher.launch(next(a for a in services.plans.get_snapshot(MODULE).agenda if a.kind == "chat"))
    assert ctx.quick_chat.calls == [dict(module_id=MODULE, prefill="Hỏi mình về sở thích", auto_send=True, display_text=None)]
    assert "a-chat" in services.plans.done_ids(MODULE)


def test_chat_without_prompt_uses_title_prefill(memory_engine):
    _tab_, services, ctx, launcher = _tab(memory_engine, agenda=[{"id": "c", "kind": "chat", "title": "Luyện nói"}])
    launcher.launch(services.plans.get_snapshot(MODULE).agenda[0])
    assert ctx.quick_chat.calls[0]["prefill"] == "Mình bắt đầu: Luyện nói"


def test_task_kind_marks_done_without_dialog(memory_engine):
    _tab_, services, _ctx, launcher = _tab(memory_engine)
    launcher.launch(next(a for a in services.plans.get_snapshot(MODULE).agenda if a.kind == "task"))
    assert "a-task" in services.plans.done_ids(MODULE)


def test_quiz_kind_with_items_opens_popup_limited_by_minutes(memory_engine):
    _tab_, services, _ctx, launcher = _tab(memory_engine)
    services.items.insert_items_dedup(
        MODULE, [quiz(f"T{i}", topic="english.tenses") for i in range(6)] + [quiz("Other", topic="math.eq")], LOCAL_NOW)
    assert quiz_limit_for_agenda(10) == 5 and quiz_limit_for_agenda(None) == 3
    items = build_session_items(services, 5, "english.tenses")
    assert len(items) == 5 and all(i.topic == "english.tenses" for i in items)
    assert [i.topic for i in build_session_items(services, 8, "math.eq")][0] == "math.eq"   # bù câu đến hạn topic khác
    launcher.launch(services.plans.get_snapshot(MODULE).agenda[0])


def test_quiz_session_empty_without_loop_says_preparing(memory_engine):
    _tab_, services, ctx, launcher = _tab(memory_engine)
    launcher.start_quiz_session(20)
    assert ctx.bubble.shown[-1]["text"] == "Ted đang soạn câu hỏi…"


async def test_step_kind_requests_single_step_item_then_opens_dialog(memory_engine):
    calls: list = []
    batch = {"items": [{"topic": "math.eq", "type": "step", "question": "Giải 2x=4", "answer": "x=2", "hints": ["chia 2"]}]}
    get_qapp()
    services, ctx = make_services(memory_engine, hermes_client([f"<json>{json.dumps(batch)}</json>"], calls))
    save_plan(services, **PLAN)
    launcher = AgendaKindLauncher(services)
    launcher.launch(next(a for a in services.plans.get_snapshot(MODULE).agenda if a.kind == "step"))
    await _drain()
    request = json.loads(calls[0]["messages"][-1]["content"].split("<json>")[1].split("</json>")[0])
    assert request["types"] == ["step"] and request["count"] == 1 and request["topic"] == "math.eq"
    from src.engines.coach.agenda_kind_launcher import _open_dialogs
    from src.ui.quiz.step_problem_dialog import StepProblemDialog
    dialog = next(d for d in _open_dialogs if isinstance(d, StepProblemDialog))
    dialog.step_widget.btn_pass.click()
    assert "a-step" in services.plans.done_ids(MODULE)


async def test_writing_dialog_offline_keeps_text_then_regrade_marks_done(memory_engine):
    graded = '<json>{"overall": 8, "scores": {"grammar": 8}}</json>'
    get_qapp()
    services, ctx = make_services(memory_engine, hermes_client([httpx.ConnectError("down"), graded]))
    launcher = AgendaKindLauncher(services)
    shown: list = []
    dialog = WritingSubmitDialog(launcher.writing_service, "Tả gia đình", "a-write", "hsk.w",
                                 on_graded=lambda: services.mark_done("a-write"), show_dialog=shown.append)
    dialog.editor.setPlainText("我的家有四口人")
    assert dialog.counter_label.text().startswith("1 từ")
    dialog.btn_submit.click()
    await _drain()
    assert dialog.btn_submit.text() == "Chấm lại" and dialog.btn_submit.isEnabled()
    assert "a-write" not in services.plans.done_ids(MODULE)
    assert len(services.plans.ungraded_submissions(MODULE)) == 1
    dialog.btn_submit.click()
    await _drain()
    assert shown and "a-write" in services.plans.done_ids(MODULE)
    assert services.plans.ungraded_submissions(MODULE) == []


async def test_regrade_from_history_marks_agenda_done_and_survives_deleted_tab(memory_engine):
    graded = '<json>{"overall": 6}</json>'
    get_qapp()
    services, ctx = make_services(memory_engine, hermes_client([graded]))
    engine = CoachModuleEngine(services.manifest, ctx, services=services)
    tab = engine.build_dashboard_tab()
    row = services.plans.add_writing_submission(MODULE, "Đề", "bài", LOCAL_NOW, agenda_id="a-write")
    engine.launcher.regrade_writing(row.id)
    delete(tab)                                   # tab bị huỷ trong lúc coroutine nền đang chạy (Red Team #3)
    await _drain()
    assert not isValid(tab) and "a-write" in services.plans.done_ids(MODULE)


def test_engine_actions_review_now_ask_sync_progress(memory_engine):
    get_qapp()
    services, ctx = make_services(memory_engine)
    engine = CoachModuleEngine(services.manifest, ctx, services=services)
    engine.handle_action("ask")
    assert ctx.quick_chat.calls[0]["module_id"] == MODULE and ctx.quick_chat.calls[0]["prefill"] is None
    engine.handle_action("sync")                 # mặc định chạy sync thật ở nền; không có event loop → bỏ qua, không lỗi
    hooked: list = []
    engine.sync_handler = lambda: hooked.append(1)
    engine.handle_action("sync")
    engine.services.request_sync()
    assert hooked == [1, 1]
    engine.handle_action("review_now")
    assert ctx.bubble.shown[-1]["text"] == "Ted đang soạn câu hỏi…"      # kho rỗng
    engine.handle_action("progress")                                       # dashboard None → không lỗi
    engine.handle_action("không-có")


def test_engine_build_tab_is_fresh_each_call_and_progress_selects_section(memory_engine):
    get_qapp()
    services, ctx = make_services(memory_engine)
    engine = CoachModuleEngine(services.manifest, ctx, services=services)
    first, second = engine.build_dashboard_tab(), engine.build_dashboard_tab()
    assert first is not second
    second.show_progress()
    assert second.currentWidget() is second.progress


def test_engine_start_and_stop_without_event_loop_do_not_raise(memory_engine):
    get_qapp()
    services, ctx = make_services(memory_engine)
    engine = CoachModuleEngine(services.manifest, ctx, services=services)
    engine.start()
    assert engine.scheduler._timer.isActive() and engine.reminders._timer.isActive()
    engine.stop()
    assert not engine.scheduler._timer.isActive()
