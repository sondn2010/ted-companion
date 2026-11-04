"""Vòng review 2 (dữ liệu + UI): agenda done theo kế hoạch hiện tại (H2), nhắc kế hoạch cũ (M3),
launcher chat/regrade (M6/L7), dòng bài viết hỏng, escape rich text (L6)."""

import asyncio
from datetime import datetime, timedelta

from coach_test_support import MODULE
from coach_ui_test_support import LOCAL_NOW, LOCAL_TZ, make_services, save_plan
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QLabel
from qt_offscreen_app_helper import get_qapp

from src.engines.coach.agenda_kind_launcher import AgendaKindLauncher
from src.engines.coach.coach_reminder_service import CoachReminderService
from src.ui.module_tabs.coach_module_tab_widget import CoachModuleTabWidget
from src.ui.quiz.writing_submit_dialog import WritingSubmitDialog

AGENDA = [{"id": "a1", "kind": "task", "title": "Việc", "when": "19:30"}]


def _at(h, m=0, day=19):
    return datetime(2026, 10, day, h, m, tzinfo=LOCAL_TZ)


# ---- H2 ----
def test_reported_done_from_old_plan_does_not_show_on_new_plan_with_reused_id(memory_engine):
    services, _ctx = make_services(memory_engine, now=_at(9, day=18))
    plans = services.plans
    save_plan(services, agenda=AGENDA)
    services.mark_done("a1")
    assert plans.done_ids(MODULE) == {"a1"}
    services._clock = lambda: _at(9)
    plans.save_sync(MODULE, plans.get_snapshot(MODULE), services.now(), reported_ids=["a1"])   # hôm qua đã báo, kế hoạch mới dùng lại "a1"
    assert plans.done_ids(MODULE) == set()
    services._clock = lambda: _at(10)
    services.mark_done("a1")                                    # làm lại hôm nay: tick được và sẽ báo lần nữa
    assert plans.done_ids(MODULE) == {"a1"} and plans.unreported_done_ids(MODULE) == ["a1"]


def test_unreported_done_survives_sync_that_started_before_tick(memory_engine):
    services, _ctx = make_services(memory_engine)
    save_plan(services, agenda=AGENDA)
    services.mark_done("late")                                  # tick trong lúc sync bay → không nằm trong reported_ids
    services._clock = lambda: LOCAL_NOW + timedelta(seconds=5)
    services.plans.save_sync(MODULE, services.plans.get_snapshot(MODULE), services.now(), reported_ids=[])
    assert "late" in services.plans.done_ids(MODULE)


def test_unmark_done_only_before_reported(memory_engine):
    services, _ctx = make_services(memory_engine)
    save_plan(services)
    services.mark_done("c1")
    assert services.plans.unmark_done(MODULE, "c1") is True and services.plans.done_ids(MODULE) == set()
    services.mark_done("c1")
    services._clock = lambda: LOCAL_NOW + timedelta(minutes=1)
    services.plans.save_sync(MODULE, services.plans.get_snapshot(MODULE), services.now(), reported_ids=["c1"])
    assert services.plans.unmark_done(MODULE, "c1") is False


def _progress_tab(engine, **plan):
    get_qapp()
    services, ctx = make_services(engine)
    save_plan(services, **plan)
    tab = CoachModuleTabWidget(services, AgendaKindLauncher(services))
    services.on_changed = tab.refresh
    return tab, services, ctx


def _box(tab, text):
    return next(b for b in tab.progress.findChildren(QCheckBox) if b.text().startswith(text))


def test_checklist_tick_can_be_undone_before_report_and_hermes_wins_after(memory_engine):
    tab, services, _ctx = _progress_tab(memory_engine, checklist=[{"id": "c1", "title": "Học 50 từ"}])
    _box(tab, "Học 50").setChecked(True)
    assert "c1" in services.plans.done_ids(MODULE)
    box = _box(tab, "Học 50")
    assert box.isChecked() and box.isEnabled()                  # còn hoàn tác được
    box.setChecked(False)
    assert services.plans.done_ids(MODULE) == set()
    _box(tab, "Học 50").setChecked(True)
    services._clock = lambda: LOCAL_NOW + timedelta(minutes=1)
    services.plans.save_sync(MODULE, services.plans.get_snapshot(MODULE), services.now(), reported_ids=["c1"])
    tab.refresh()
    assert not _box(tab, "Học 50").isChecked()                  # đã báo: Hermes (status=todo) quyết định


# ---- M3 ----
def test_yesterdays_agenda_not_reminded_until_synced_today_and_tab_labels_stale(memory_engine):
    get_qapp()
    services, ctx = make_services(memory_engine, now=_at(19, 30, day=18))
    save_plan(services, agenda=AGENDA)
    services._clock = lambda: _at(19, 30)                       # hôm nay, chưa sync
    svc = CoachReminderService(services, lambda item: None)
    assert svc.check() == "none" and ctx.bubble.shown == []
    tab = CoachModuleTabWidget(services, AgendaKindLauncher(services))
    assert "Kế hoạch từ 18/10" in tab.today.sync_label.text()
    save_plan(services, agenda=AGENDA)                          # sync hôm nay
    assert svc.check() == "agenda"
    tab.today.refresh()
    assert "Kế hoạch từ" not in tab.today.sync_label.text()


# ---- M6 / L7 ----
def _chat_item():
    from src.engines.coach.coach_sync_plan_schemas import AgendaItem
    return AgendaItem(id="chat1", kind="chat", title="Luyện nói", prompt="Hỏi mình đi")


def test_chat_marked_done_only_when_open_for_sent(memory_engine):
    get_qapp()
    services, ctx = make_services(memory_engine)
    launcher = AgendaKindLauncher(services)
    ctx.quick_chat.refuse = True
    launcher.open_chat(_chat_item())
    assert services.plans.done_ids(MODULE) == set() and "bận" in ctx.bubble.shown[-1]["text"]
    ctx.quick_chat.refuse = False
    launcher.open_chat(_chat_item())
    assert services.plans.done_ids(MODULE) == {"chat1"}


async def test_regrade_in_flight_guard_runs_once(memory_engine, monkeypatch):
    get_qapp()
    services, _ctx = make_services(memory_engine)
    launcher = AgendaKindLauncher(services)
    calls: list = []

    async def slow_regrade(sid, minutes=0):
        calls.append(sid)
        await asyncio.sleep(0.03)
        return type("O", (), {"result": None})()

    monkeypatch.setattr(launcher.writing_service, "regrade", slow_regrade)
    launcher.regrade_writing("s1")
    launcher.regrade_writing("s1")
    await asyncio.sleep(0.08)
    assert calls == ["s1"] and not launcher._regrading
    launcher.regrade_writing("s1")                              # xong rồi → bấm lại được
    await asyncio.sleep(0.08)
    assert calls == ["s1", "s1"]


def test_corrupt_graded_row_does_not_break_progress_tab(memory_engine):
    tab, services, _ctx = _progress_tab(memory_engine)
    good = services.plans.add_writing_submission(MODULE, "Đề tốt", "bài", LOCAL_NOW)
    bad = services.plans.add_writing_submission(MODULE, "Đề hỏng", "bài", LOCAL_NOW + timedelta(seconds=1))
    from src.engines.coach.coach_data_models import WritingSubmission, open_session
    with open_session(services.db_engine) as session:
        row = session.get(WritingSubmission, bad.id)
        row.result_json = '{"overall": "không phải số"'
        session.add(row)
        session.commit()
    tab.progress.refresh()
    texts = [w.text() for w in tab.progress.findChildren(QLabel)]
    assert any("Đề hỏng" in t and "hỏng" in t for t in texts) and any("Đề tốt" in t for t in texts)
    assert good.id != bad.id


# ---- L6 ----
def test_hermes_text_in_labels_is_plain_not_rich(memory_engine):
    evil = "<img src=x> <b>đậm</b>"
    tab, _s, _c = _progress_tab(
        memory_engine, display={"title": evil}, agenda=[{"id": "a1", "kind": "quiz", "title": evil}],
        milestones=[{"id": "m1", "title": evil, "due_date": "2026-12-01"}])
    labels = [w for w in tab.findChildren(QLabel) if evil in w.text()]
    assert len(labels) >= 3                                     # tiêu đề, agenda, mốc
    assert all(w.textFormat() == Qt.TextFormat.PlainText for w in labels)


def test_writing_dialog_prompt_is_escaped(memory_engine):
    get_qapp()
    services, _ctx = make_services(memory_engine)
    from src.engines.coach.writing_submission_service import WritingSubmissionService
    dialog = WritingSubmitDialog(WritingSubmissionService(services), "<img src=x>Tả <i>mẹ</i>")
    label = next(w for w in dialog.findChildren(QLabel) if w.text().startswith("<b>Đề:</b>"))
    assert "<img" not in label.text() and "&lt;img src=x&gt;" in label.text()
