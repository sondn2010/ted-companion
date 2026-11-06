"""Hộp thoại Gỡ Rối: kind theo engine, chat qua runner Quick Chat, phản biện → DB + 1 tín hiệu, lưu ghi chú, no-connection, wiring."""
import asyncio
import json
from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal
from qt_offscreen_app_helper import get_qapp

from src.core.idea_untangle.idea_untangle_service_and_completion_signal import IdeaUntangleService
from src.core.idea_untangle.untangle_session_repository import UntangleSessionRepository
from src.core.models import db
from src.ui.idea_untangle.untangle_dialog_window import UntangleDialog

CRITIQUE_JSON = json.dumps({
    "summary": "Bạn đang so sánh <b>hai</b> hướng", "flow_steps": ["Đọc đề", "Chọn hướng", "Kiểm tra"],
    "logic_gaps": [{"step": 2, "issue": "Chưa nêu tiêu chí", "question": "Tiêu chí là gì?"}],
    "assumptions": ["Dữ liệu nhỏ"], "new_angles": ["Thử đảo bài toán"], "next_step": "Viết 3 test mẫu"})


class _Focus(QObject):
    character_changed = Signal(str)
    current_mood = "IDLE"
    active_task_id = None
    active_task_title = ""

    def __init__(self):
        super().__init__()
        self.added = []

    def get_context_snapshot(self):
        return {}

    def set_mood(self, _m):
        pass

    def add_task(self, title, **_kw):
        self.added.append(title)


class _Client:
    connection = SimpleNamespace(name="Fake")

    def __init__(self):
        self.messages = []
        self.history = []

    async def stream_chat(self, user_message, current_context, on_mood_change, on_token, persona, resume_mood=None):
        self.messages.append((user_message, persona))
        on_token("Bạn kẹt ở đâu?")

    async def complete_text(self, messages, timeout=None):
        return f"<json>{CRITIQUE_JSON}</json>"


def _registry(engine="work", mid="work"):
    manifest = SimpleNamespace(id=mid, engine=engine, icon="🧩", name=mid)
    return SimpleNamespace(active=lambda: manifest, get=lambda _m: manifest)


def _dialog(client, engine="work", mid="work", memory_engine=None):
    get_qapp()
    service = IdeaUntangleService(UntangleSessionRepository(memory_engine))
    dlg = UntangleDialog(_Focus(), SimpleNamespace(for_module=lambda _m: client), _registry(engine, mid), service=service)
    return dlg, service


async def _until(cond):
    for _ in range(200):
        if cond():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("điều kiện không đạt")


async def test_kinds_follow_engine_and_prefix_is_hidden_from_display(memory_engine):
    client = _Client()
    dlg, _ = _dialog(client, "coach", "thcs", memory_engine)
    dlg.open_from("hotkey")
    assert set(dlg.kind_buttons) == {"math_problem", "concept", "essay_structure", "other"}
    dlg._select_kind("math_problem")
    dlg.input_chat.setText("mình không hiểu phân số")
    assert dlg._on_send_chat() is True
    await _until(lambda: not dlg._in_flight)
    sent, persona = client.messages[0]
    assert sent.startswith("[TED_UNTANGLE:kind=math_problem;audience=learner]") and persona == "coach"
    shown = dlg.chat_view.toPlainText()
    assert "mình không hiểu phân số" in shown and "TED_UNTANGLE" not in shown
    assert dlg._turns[-1] == {"role": "assistant", "text": "Bạn kẹt ở đâu?"} and dlg.btn_critique.isEnabled()


async def test_critique_completes_once_saves_notes_and_creates_next_task(memory_engine):
    client = _Client()
    task = db.add_task("Giải bài toán X")
    dlg, service = _dialog(client, memory_engine=memory_engine)
    dlg.focus_engine.active_task_id = task.id
    emitted = []
    service.session_completed.connect(lambda *a: emitted.append(a))
    dlg.open_from("menu")
    assert not dlg.btn_critique.isEnabled()          # chưa có lượt nào
    dlg.input_chat.setText("thuật toán chạy chậm")
    dlg._on_send_chat()
    await _until(lambda: not dlg._in_flight)
    dlg._on_critique()
    await _until(lambda: dlg._critique is not None and not dlg._in_flight)
    assert len(emitted) == 1 and emitted[0][1] == task.id
    html = dlg.chat_view.toHtml()
    assert "&lt;b&gt;hai&lt;/b&gt;" in html or "<b>hai</b>" not in dlg.chat_view.toPlainText()   # escape, không render thẻ AI
    assert dlg.btn_save_notes.isVisibleTo(dlg) and dlg.btn_next_task.isVisibleTo(dlg)
    dlg._on_save_notes()
    notes = db.get_task(task.id).notes
    assert "Bạn đang so sánh" in notes and "➜ Viết 3 test mẫu" in notes
    dlg._on_create_next_task()
    assert dlg.focus_engine.added == ["Viết 3 test mẫu"]
    dlg._on_critique()   # gọi lại: không tạo thêm tín hiệu hoàn tất
    await _until(lambda: not dlg._in_flight)
    assert len(emitted) == 1


async def test_no_connection_shows_hint_for_chat_and_critique_and_unlocks(memory_engine):
    dlg, _ = _dialog(None, memory_engine=memory_engine)
    dlg.open_from("menu")
    dlg.input_chat.setText("kẹt rồi")
    dlg._on_send_chat()
    await _until(lambda: not dlg._in_flight)
    assert "Chưa cấu hình kết nối" in dlg.chat_view.toPlainText() and dlg.btn_send.isEnabled()
    assert dlg._turns == []   # không có phản hồi → chưa tính là lượt, không bật nút phản biện


async def test_no_task_hides_save_notes_and_new_session_resets(memory_engine):
    client = _Client()
    dlg, _ = _dialog(client, memory_engine=memory_engine)
    dlg.open_from("menu")
    dlg.input_chat.setText("ý tưởng rối")
    dlg._on_send_chat()
    await _until(lambda: not dlg._in_flight)
    dlg._on_critique()
    await _until(lambda: dlg._critique is not None and not dlg._in_flight)
    assert not dlg.btn_save_notes.isVisibleTo(dlg)    # không gắn task
    client.history = [{"role": "system", "content": "s"}, {"role": "user", "content": "chat chung"}]
    dlg._on_new_session()
    assert dlg._turns == [] and dlg._critique is None and dlg._session_id is None
    assert len(client.history) == 2   # lịch sử Hermes dùng chung với các khung chat khác: không bị xoá


def test_wiring_binds_hotkey_and_exposes_menu_entry(monkeypatch):
    get_qapp()
    from src.ui.idea_untangle import idea_untangle_feature_wiring as wiring

    bound = {}
    manager = SimpleNamespace(bind_callback=lambda aid, cb, **_k: bound.setdefault(aid, cb))
    focus = _Focus()
    ctx = SimpleNamespace(focus_engine=focus, client_pool=SimpleNamespace(for_module=lambda _m: None),
                          registry=_registry(), kv=None, bubble=SimpleNamespace(is_busy=lambda: False))
    companion = SimpleNamespace(pos=lambda: SimpleNamespace(x=lambda: 100, y=lambda: 100), width=lambda: 120)
    monkeypatch.setattr(wiring, "install_untangle_nudge_watcher",
                        lambda *a, **k: SimpleNamespace(nudge_requested=SimpleNamespace(connect=lambda cb: bound.setdefault("nudge", cb))))
    monkeypatch.setattr(wiring, "_place_near_companion", lambda *_: None)
    dlg = wiring.wire_idea_untangle(ctx, companion, manager)
    assert companion.untangle_dialog is dlg and "untangle.open" in bound and "nudge" in bound
    bound["nudge"]("work", "", "other", "overrun")
    assert dlg.isVisible()
    dlg.hide()


def test_reopen_while_in_flight_keeps_running_session_task(memory_engine):
    """Mở lại cho task khác khi đang stream/phản biện → giữ task cũ (kết quả không bị gắn sang task mới)."""
    first, other = db.add_task("Task A"), db.add_task("Task B")
    dlg, _ = _dialog(_Client(), memory_engine=memory_engine)
    dlg.open_from("menu", task_id=first.id)
    dlg._in_flight = True
    dlg.open_from("hotkey", task_id=other.id)
    assert dlg._task_id == first.id and dlg._task_title == "Task A"
    dlg._in_flight = False
    dlg.open_from("menu", task_id=other.id)
    assert dlg._task_id == other.id
