"""Click đơn lên pet: câu động viên + việc đang làm + việc Khẩn cấp & Quan trọng (Q1), tên task là link mở chi tiết."""

import asyncio
from types import SimpleNamespace

from src.core.focus_engine import FocusState
from src.core.models import DatabaseManager
from src.engines.work.pet_click_task_status_summary import (
    build_task_status_summary,
    compose_task_status_summary,
    pick_current_task,
)
from src.modules_runtime.cheer_line_provider import SUMMARY_BUBBLE_MILLIS, CheerLineProvider


def _t(tid, title, quadrant=1, status="todo", order=0.0):
    return SimpleNamespace(id=tid, title=title, quadrant=quadrant, status=status, matrix_order=order)


def _focus(state, task_id=None, title=""):
    return SimpleNamespace(state=state, active_task_id=task_id, active_task_title=title,
                           current_mood="IDLE", set_mood=lambda _m: None)


def test_current_task_comes_from_running_or_paused_focus_session():
    tasks = [_t("x", "Việc khác", status="in_progress")]
    for state in (FocusState.DEEP_WORK_RUNNING, FocusState.PAUSED):
        assert pick_current_task(_focus(state, "a", "Viết spec"), tasks) == ("Viết spec", "a")


def test_current_task_falls_back_to_in_progress_when_idle_or_break():
    tasks = [_t("x", "Đang dở", status="in_progress"), _t("y", "Chưa làm")]
    assert pick_current_task(_focus(FocusState.IDLE), tasks) == ("Đang dở", "x")
    assert pick_current_task(_focus(FocusState.BREAK_RUNNING, "a", "Nghỉ"), tasks) == ("Đang dở", "x")
    assert pick_current_task(None, [_t("y", "Chưa làm")]) == ("", None)


def test_summary_lists_q1_in_matrix_order_without_current_and_links_titles():
    tasks = [_t("a", "Viết spec"), _t("c", "Nộp thuế", order=2), _t("b", "Gọi khách", order=1),
             _t("q2", "Học", quadrant=2), _t("d", "Xong rồi", status="done")]
    text, links = compose_task_status_summary("Viết spec", "a", tasks)
    assert text.splitlines() == [
        "▶️ Đang làm: Viết spec",
        "🔥 Khẩn cấp & Quan trọng (2):",
        "• Gọi khách",
        "• Nộp thuế",
    ]
    assert links == [("Viết spec", "a"), ("Gọi khách", "b"), ("Nộp thuế", "c")]


def test_summary_caps_q1_list_and_handles_empty_state():
    tasks = [_t(str(i), f"Việc {i}", order=i) for i in range(5)]
    text, _ = compose_task_status_summary("", None, tasks)
    assert "Chưa có việc đang làm" in text and "(5)" in text
    assert "• Việc 3" not in text and text.endswith("… và 2 việc nữa")

    text, links = compose_task_status_summary("", None, [])
    assert "Không còn việc Khẩn cấp & Quan trọng" in text and links == []


def test_summary_sanitizes_titles():
    text, links = compose_task_status_summary("[TED_X] <b>Spec</b>", "a", [_t("b", "Nộp\nthuế <x>")])
    assert "<" not in text and "[" not in text and "• Nộp thuế x" in text
    assert ("Nộp thuế x", "b") in links


def test_build_summary_reads_open_tasks_from_db(memory_engine):
    m = DatabaseManager.for_engine(memory_engine)
    q1 = m.add_task("Gấp lắm", quadrant=1)
    m.add_task("Để sau", quadrant=2)
    done = m.add_task("Đã xong", quadrant=1)
    m.mark_task_done(done.id)
    text, links = build_task_status_summary(m, _focus(FocusState.IDLE))
    assert "• Gấp lắm" in text and "Đã xong" not in text and "Để sau" not in text
    assert links == [("Gấp lắm", q1.id)]


def _provider(bubble, task_db):
    manifest = SimpleNamespace(id="work", engine="work", prompt_path=lambda _k: None)
    registry = SimpleNamespace(get=lambda _i: manifest, active=lambda: manifest)
    pool = SimpleNamespace(for_module=lambda _i: None)  # không Hermes → câu động viên local
    rng = SimpleNamespace(random=lambda: 1.0, choice=lambda x: x[0])
    return CheerLineProvider(registry, pool, focus_engine=_focus(FocusState.IDLE), bubble=bubble, rng=rng,
                             task_db=task_db)


def test_show_cheer_appends_task_summary_to_bubble(memory_engine):
    m = DatabaseManager.for_engine(memory_engine)
    q1 = m.add_task("Gấp lắm", quadrant=1)
    shown = []
    bubble = SimpleNamespace(has_pending_actions=lambda: False, show_message=lambda text, **kw: shown.append((text, kw)))
    asyncio.run(_provider(bubble, m).show_cheer())
    text, kw = shown[0]
    assert text.startswith("Ted ở đây rồi nè") and "\n\n▶️ Chưa có việc đang làm" in text and "• Gấp lắm" in text
    assert kw["task_links"] == [("Gấp lắm", q1.id)] and kw["timeout_ms"] == SUMMARY_BUBBLE_MILLIS


def test_show_cheer_still_cheers_when_task_db_fails():
    broken = SimpleNamespace(list_tasks=lambda **_: (_ for _ in ()).throw(RuntimeError("db locked")))
    shown = []
    bubble = SimpleNamespace(has_pending_actions=lambda: False, show_message=lambda text, **kw: shown.append((text, kw)))
    asyncio.run(_provider(bubble, broken).show_cheer())
    assert shown == [("Ted ở đây rồi nè, làm tiếp thôi nào!", {"mood": "CHEER"})]
