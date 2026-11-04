"""Onboarding end-to-end: quick chat stream thật (SSE qua MockTransport) → khối {"onboarding":"done"} bị ẩn → sync lại.
Cùng với persona chat (coach không nhận prompt/header của work) và 3 manifest coach built-in."""

import asyncio
import json
from types import SimpleNamespace

import httpx
from coach_test_support import MODULE
from coach_ui_test_support import LOCAL_NOW, MANIFEST, make_services
from PySide6.QtCore import QObject, Signal
from qt_offscreen_app_helper import get_qapp

from src.bridge.hermes_client import SYSTEM_FALLBACK_PROMPT, HermesBrainClient
from src.core.background_task_spawner import _running_tasks
from src.core.connection_registry_and_settings_migration import HermesConnection
from src.engines.coach.coach_module_engine import CoachModuleEngine
from src.modules_runtime.module_registry_loader import default_module_dirs, load_manifests
from src.ui.quick_chat_popup import QuickChatPopup

PLAN = {"display": {"title": "Ôn thi"}, "agenda": [{"id": "a1", "kind": "task", "title": "Làm quen xong"}]}
DONE_BLOCK = '<json>{"onboarding":"done","learner":"con"}</json>'


class _Focus(QObject):
    character_changed = Signal(str)
    current_mood = "IDLE"

    def get_context_snapshot(self):
        return {"status": "IDLE"}

    def set_mood(self, mood):
        pass


def _sse(pieces):
    body = "".join("data: " + json.dumps({"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "m",
                                          "choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}]},
                                         ensure_ascii=False) + "\n\n" for p in pieces) + "data: [DONE]\n\n"
    return httpx.Response(200, content=body.encode("utf-8"), headers={"content-type": "text/event-stream"})


def _client(stream_pieces, complete_replies, sent):
    queue = list(complete_replies)

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        if body.get("stream"):
            return _sse(stream_pieces)
        content = queue.pop(0)
        return httpx.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": "m", "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]})

    conn = HermesConnection(id="t", name="T", base_url="http://hermes.test/v1", api_key="k")
    return HermesBrainClient(conn, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def _drain():
    while _running_tasks:
        await asyncio.gather(*list(_running_tasks))


async def test_onboarding_chat_hides_done_block_and_triggers_sync(memory_engine):
    get_qapp()
    sent: list[dict] = []
    client = _client(["[MOOD:CHEER] Chào con! Mình xong rồi nhé. ", "<js", "on>" + DONE_BLOCK[6:]],
                     ["<json>" + json.dumps(PLAN) + "</json>"], sent)
    services, ctx = make_services(memory_engine, client)
    popup = QuickChatPopup(_Focus(), SimpleNamespace(for_module=lambda _m: client), SimpleNamespace(
        active=lambda: None, get=lambda module_id: MANIFEST))
    ctx.quick_chat = popup
    engine = CoachModuleEngine(MANIFEST, ctx, services=services)
    engine.start()
    services.set_needs_onboarding(True)

    engine.onboarding.start()                       # = nút [Bắt đầu] của bong bóng / banner
    await _drain()

    chat = popup.chat_view.toPlainText()
    assert "Bắt đầu làm quen" in chat and "TED_ONBOARDING" not in chat
    assert "Chào con! Mình xong rồi nhé." in chat and "<json>" not in chat and "onboarding" not in chat
    onboarding_request = sent[0]["messages"]
    assert [m["role"] for m in onboarding_request] == ["user"]                    # coach: không system prompt của work
    assert onboarding_request[0]["content"].startswith("[TED_STATE: status=IDLE]\n[TED_ONBOARDING]")
    assert "today_completed_pomodoros" not in onboarding_request[0]["content"]
    assert '"learner": "con"' in onboarding_request[0]["content"]
    # lịch sử giữ lượt mở đầu onboarding, không giữ khối json
    assert client.history[1]["content"].startswith("[TED_ONBOARDING]") and "<json>" not in client.history[2]["content"]
    # sync tự chạy sau onboarding → agenda xuất hiện, cờ onboarding xoá, bong bóng báo
    assert [a.id for a in services.plans.get_snapshot(MODULE).agenda] == ["a1"]
    assert not services.needs_onboarding() and "Đã cập nhật kế hoạch" in ctx.bubble.shown[-1]["text"]
    engine.stop()
    assert MODULE not in popup._reply_json_handlers


async def test_done_block_ignored_for_other_learner_or_other_json(memory_engine):
    get_qapp()
    services, ctx = make_services(memory_engine, _client([], [], []))
    engine = CoachModuleEngine(MANIFEST, ctx, services=services)
    services.set_needs_onboarding(True)
    engine._on_reply_json({"onboarding": "done", "learner": "bo"})
    engine._on_reply_json({"foo": "bar"})
    await _drain()
    assert services.needs_onboarding() and services.plans.get_snapshot(MODULE) is None


async def test_work_persona_keeps_system_prompt_and_analytics_header():
    sent: list[dict] = []
    client = _client(["[MOOD:FOCUS] ok"], [], sent)
    await client.stream_chat("hi", {"status": "IDLE", "task": "x", "remaining_mins": 1}, lambda _m: None, lambda _t: None)
    assert sent[0]["messages"][0] == {"role": "system", "content": SYSTEM_FALLBACK_PROMPT}
    assert "today_completed_pomodoros" in sent[0]["messages"][-1]["content"]


def test_coach_tab_banner_follows_onboarding_flag(memory_engine):
    get_qapp()
    services, ctx = make_services(memory_engine)
    engine = CoachModuleEngine(MANIFEST, ctx, services=services)
    tab = engine.build_dashboard_tab()
    assert tab.today.onboarding_banner.isHidden()
    services.set_needs_onboarding(True)
    tab.refresh()
    assert not tab.today.onboarding_banner.isHidden()
    services.start_onboarding()
    assert ctx.quick_chat.calls[-1]["display_text"] == "Bắt đầu làm quen" and ctx.quick_chat.calls[-1]["auto_send"]


async def test_engine_daily_sync_only_when_due(memory_engine):
    get_qapp()
    plan = "<json>" + json.dumps(PLAN) + "</json>"
    services, ctx = make_services(memory_engine, _client([], [plan, plan], []))
    engine = CoachModuleEngine(MANIFEST, ctx, services=services)
    engine.maybe_daily_sync()
    await _drain()
    assert services.plans.get_snapshot(MODULE) is not None and ctx.bubble.shown == []   # tự động: im lặng
    first_synced = services.plans.get_synced_at(MODULE)
    engine.maybe_daily_sync()                                                           # cùng ngày → không sync
    await _drain()
    assert services.plans.get_synced_at(MODULE) == first_synced
    engine.handle_action("sync")                                                        # thủ công → luôn sync + bubble
    await _drain()
    assert "Đã cập nhật kế hoạch" in ctx.bubble.shown[-1]["text"]


def test_builtin_coach_manifests_match_docs_and_default_disabled():
    manifests, errors = load_manifests(default_module_dirs()[:1])
    assert errors == []
    expected = {"thcs": ("con", 20), "duhoc": ("con", 30), "caohoc": ("bo", 40)}
    for module_id, (learner, order) in expected.items():
        m = manifests[module_id]
        assert (m.engine, m.connection, m.learner_id, m.order, m.enabled) == ("coach", module_id, learner, order, False)
    assert manifests["work"].settings["share_meeting_titles"] is False
