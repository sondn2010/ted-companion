"""Quiz popup, bảng phản hồi, hộp thoại step: chạy widget thật (offscreen) trên DB in-memory."""

import json
import re

from coach_test_support import MODULE, quiz
from coach_ui_test_support import LOCAL_NOW, make_services
from qt_offscreen_app_helper import get_qapp

from src.engines.coach.coach_quiz_session_service import EXPLAIN_DISPLAY_TEXT, CoachQuizSessionService
from src.ui.quiz.quiz_answer_feedback_panel import AnswerFeedbackPanel
from src.ui.quiz.quiz_popup_dialog import QuizPopupDialog
from src.ui.quiz.step_problem_dialog import StepProblemDialog


def _setup(engine, generated):
    get_qapp()
    services, ctx = make_services(engine)
    services.items.insert_items_dedup(MODULE, generated, LOCAL_NOW)
    items = services.items.select_for_review(MODULE, LOCAL_NOW, 50, 50, LOCAL_NOW)
    by_q = {i.question: i for i in items}
    return services, ctx, CoachQuizSessionService(services), by_q


def _panel(dialog) -> AnswerFeedbackPanel:
    assert isinstance(dialog._body, AnswerFeedbackPanel)
    return dialog._body


def test_mcq_correct_cheers_and_wrong_shows_answer(memory_engine):
    services, ctx, svc, by_q = _setup(memory_engine, [quiz("M1", type_="mcq"), quiz("M2", type_="mcq")])
    done: list = []
    dialog = QuizPopupDialog([by_q["M1"], by_q["M2"]], svc, ctx.focus_engine.set_mood, lambda a, c: done.append((a, c)))
    dialog._body.choice_buttons[1].click()                      # B đúng
    assert ctx.focus_engine.moods == ["CHEER"]
    _panel(dialog).btn_next.click()
    dialog._body.choice_buttons[0].click()                      # A sai
    assert "Đáp án: B" in _panel(dialog).detail_label.text()
    assert _panel(dialog).btn_explain.text() == "Vì sao sai? Hỏi gia sư"
    _panel(dialog).btn_next.click()
    assert done == [(2, 1)]                                     # chỉ hoàn tất khi hết phiên


def test_early_close_does_not_complete_session(memory_engine):
    services, ctx, svc, by_q = _setup(memory_engine, [quiz("M1", type_="mcq"), quiz("M2", type_="mcq")])
    done: list = []
    dialog = QuizPopupDialog([by_q["M1"], by_q["M2"]], svc, on_completed=lambda a, c: done.append(1))
    dialog._body.choice_buttons[1].click()
    dialog.close()
    assert done == []


def test_wrong_answer_comes_back_after_first_leitner_interval(memory_engine):
    services, ctx, svc, by_q = _setup(memory_engine, [quiz("S1", answer="đúng")])
    item = by_q["S1"]
    svc.submit(item, "sai")
    assert services.items.due_count(MODULE, LOCAL_NOW) == 0
    # leitner_days[0] ≈ 10 phút (0.007 ngày) → đến hạn ở tick kế tiếp đủ điều kiện
    from datetime import timedelta
    assert services.items.due_count(MODULE, LOCAL_NOW + timedelta(minutes=11)) == 1


def test_short_wrong_has_regrade_and_it_is_idempotent(memory_engine):
    services, ctx, svc, by_q = _setup(memory_engine, [quiz("S1", answer="went")])
    item = by_q["S1"]
    svc.submit(item, "go")                                      # sai → hộp 0, lapses 1
    dialog = QuizPopupDialog([item], svc, ctx.focus_engine.set_mood)
    dialog._body.input.setText("goed")
    dialog._body.submit()
    panel = _panel(dialog)
    assert panel.btn_regrade.text() == "Mình đúng mà"
    panel.btn_regrade.click()
    panel.btn_regrade.click()                                   # bấm lần 2 (nút đã disable) không làm gì thêm
    state = services.attempts.load_states([item.id])[item.id]
    attempts = services.attempts.attempts_between(MODULE, LOCAL_NOW.replace(year=2000), LOCAL_NOW.replace(year=2100))
    assert state.box == 1 and state.lapses == 1                 # lần sai đầu (lapses 1) + sai lần 2 (-1)
    assert sorted(a.correct for a in attempts) == [False, True]


def test_regrade_service_second_call_returns_false(memory_engine):
    services, ctx, svc, by_q = _setup(memory_engine, [quiz("S1", answer="went")])
    result = svc.submit(by_q["S1"], "x")
    assert svc.regrade_as_correct(result.attempt_id) is True
    assert svc.regrade_as_correct(result.attempt_id) is False


def test_flag_marks_item_and_excludes_it_from_review(memory_engine):
    services, ctx, svc, by_q = _setup(memory_engine, [quiz("S1"), quiz("S2")])
    assert svc.flag(by_q["S1"], "đề sai") is True
    flagged = services.items.flagged_items(MODULE)
    assert [(f.question, f.flag_reason) for f in flagged] == [("S1", "đề sai")]
    assert [i.question for i in services.items.select_for_review(MODULE, LOCAL_NOW, 10, 10, LOCAL_NOW)] == ["S2"]
    services.items.unflag_item(flagged[0].id)
    assert services.items.flagged_items(MODULE) == []


def test_panel_flag_signal_carries_reason(memory_engine):
    services, ctx, svc, by_q = _setup(memory_engine, [quiz("S1", answer="a")])
    dialog = QuizPopupDialog([by_q["S1"]], svc)
    dialog._body.input.setText("b")
    dialog._body.submit()
    panel = _panel(dialog)
    panel.btn_flag.click()
    panel.flag_input.setText("đáp án sai")
    panel.flag_input.returnPressed.emit()
    assert services.items.flagged_items(MODULE)[0].flag_reason == "đáp án sai"


def test_explain_sends_envelope_with_display_text(memory_engine):
    services, ctx, svc, by_q = _setup(memory_engine, [quiz("M1", topic="english.conditionals", type_="mcq")])
    item = by_q["M1"]
    svc.ask_tutor(item, "A")
    call = ctx.quick_chat.calls[0]
    assert call["module_id"] == MODULE and call["auto_send"] is True and call["display_text"] == EXPLAIN_DISPLAY_TEXT
    assert call["prefill"].startswith("[TED_EXPLAIN_MISTAKE]")
    payload = json.loads(re.search(r"<json>(.*)</json>", call["prefill"], re.S).group(1))
    assert payload["learner"] == "con" and payload["subject"] == "english" and payload["correct"] == "B"
    assert payload["user_answer"] == "A" and len(payload["choices"]) == 4


def test_step_hints_reveal_in_order_then_self_assess_records_attempt(memory_engine):
    services, ctx, svc, by_q = _setup(
        memory_engine, [quiz("P1", type_="step", answer="x=2", hints=["h1", "h2", "h3"], explanation="giải")])
    results: list = []
    dialog = StepProblemDialog(by_q["P1"], svc, results.append, ctx.focus_engine.set_mood)
    widget = dialog.step_widget
    assert [b.isEnabled() for b in widget.hint_buttons] == [True, False, False]
    widget.hint_buttons[0].click()
    assert [b.isEnabled() for b in widget.hint_buttons] == [False, True, False]
    widget.hint_buttons[1].click()
    widget.reveal_solution()
    assert "h1" in widget.reveal_label.text() and "h2" in widget.reveal_label.text() and "x=2" in widget.reveal_label.text()
    widget.btn_fail.click()
    assert results == [False]
    state = services.attempts.load_states([by_q["P1"].id])[by_q["P1"].id]
    assert state.box == 0 and state.lapses == 1


def test_step_pass_moves_box_up(memory_engine):
    services, ctx, svc, by_q = _setup(memory_engine, [quiz("P1", type_="step", answer="x")])
    results: list = []
    dialog = StepProblemDialog(by_q["P1"], svc, results.append, ctx.focus_engine.set_mood)
    dialog.step_widget.btn_pass.click()
    assert results == [True] and ctx.focus_engine.moods == ["CHEER"]
    assert services.attempts.load_states([by_q["P1"].id])[by_q["P1"].id].box == 1
