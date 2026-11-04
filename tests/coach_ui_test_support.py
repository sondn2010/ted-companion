"""Dụng cụ test cho Phase 07: ctx giả (focus/bubble/quick_chat/kv thật), client Hermes qua httpx.MockTransport."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
from PySide6.QtCore import QObject, Signal

from src.bridge.hermes_client import HermesBrainClient
from src.core.app_state_key_value_store import KeyValueStore
from src.core.connection_registry_and_settings_migration import HermesConnection
from src.core.focus_engine import FocusState
from src.engines.coach.coach_module_services import CoachModuleServices
from src.engines.coach.coach_sync_plan_schemas import SyncPlanPayload
from src.modules_runtime.module_manifest_schema import ModuleManifest

LOCAL_TZ = timezone(timedelta(hours=7))
LOCAL_NOW = datetime(2026, 10, 19, 12, 0, tzinfo=LOCAL_TZ)
MANIFEST = ModuleManifest(id="thcs", name="THCS", icon="📚", engine="coach", connection="thcs", learner_id="con")


class FakeFocus(QObject):
    state_changed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.state = FocusState.IDLE
        self.moods: list[str] = []

    def set_mood(self, mood: str):
        self.moods.append(mood)


class FakeBubble:
    def __init__(self):
        self.busy = False
        self.shown: list[dict] = []

    def is_busy(self) -> bool:
        return self.busy

    def show_message(self, text, mood=None, actions=(), timeout_ms=6000):
        self.shown.append({"text": text, "mood": mood, "actions": list(actions)})


class FakeQuickChat:
    def __init__(self):
        self.calls: list[dict] = []
        self.refuse = False   # True = giả lập đang có luồng trả lời → open_for từ chối (trả False)

    def open_for(self, module_id, prefill=None, auto_send=False, display_text=None) -> bool:
        self.calls.append(dict(module_id=module_id, prefill=prefill, auto_send=auto_send, display_text=display_text))
        return not self.refuse


def hermes_client(replies, calls=None):
    """replies: list nội dung assistant (hoặc callable(request_json) → str | Exception); lặp phần tử cuối."""
    calls = calls if calls is not None else []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        reply = replies[min(len(calls) - 1, len(replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return httpx.Response(200, json={
            "id": "c", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
        })

    conn = HermesConnection(id="t", name="T", base_url="http://hermes.test/v1", api_key="k")
    return HermesBrainClient(conn, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def make_services(engine, client=None, now: datetime = LOCAL_NOW):
    """(services, ctx). Đồng hồ cố định; `now` có thể đổi qua services._clock."""
    ctx = SimpleNamespace(
        focus_engine=FakeFocus(), bubble=FakeBubble(), quick_chat=FakeQuickChat(), dashboard=None,
        kv=KeyValueStore(engine), client_pool=SimpleNamespace(for_module=lambda _mid: client))
    services = CoachModuleServices(MANIFEST, ctx, engine, tz=LOCAL_TZ, clock=lambda: now)
    return services, ctx


def save_plan(services: CoachModuleServices, **fields) -> SyncPlanPayload:
    payload = SyncPlanPayload.model_validate(fields)
    return services.plans.save_sync(services.module_id, payload, services.now())
