"""Sync lịch qua HermesBrainClient thật (httpx.MockTransport) + nhắc họp offline + engine/tab."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import yaml

from tests.qt_offscreen_app_helper import get_qapp

from src.bridge.hermes_client import HermesBrainClient
from src.core.app_state_key_value_store import KeyValueStore
from src.core.connection_registry_and_settings_migration import HermesConnection
from src.engines.work.calendar_contract_schemas import CalendarEvent
from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventRepository
from src.engines.work.work_module_engine import WorkModuleEngine
from src.modules_runtime.app_runtime_context import AppRuntimeContext
from src.modules_runtime.module_manifest_schema import ModuleManifest
from src.ui.pet_speech_bubble_widget import PetSpeechBubble

WORK_DIR = Path(__file__).resolve().parent.parent / "modules" / "work"


class ChimeCounter:
    """Thay AudioManager (không phát âm thanh trong test): chỉ đếm số lần chime."""

    def __init__(self):
        self.plays = 0

    def play_chime(self):
        self.plays += 1


def _manifest() -> ModuleManifest:
    data = yaml.safe_load((WORK_DIR / "module.yaml").read_text(encoding="utf-8"))
    return ModuleManifest(**data, module_dir=WORK_DIR)


def _reply(text: str) -> httpx.Response:
    body = {"id": "c", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}]}
    return httpx.Response(200, json=body)


def _setup(memory_engine, replies):
    """replies: list content trả lần lượt (phần tử cuối lặp lại). Trả (engine, ctx, requests)."""
    get_qapp()
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return _reply(replies[min(len(requests) - 1, len(replies) - 1)])

    conn = HermesConnection(id="work", name="Work", base_url="http://hermes.test/v1", api_key="k")
    client = HermesBrainClient(conn, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    ctx = AppRuntimeContext(
        kv=KeyValueStore(memory_engine), bubble=PetSpeechBubble(), audio=ChimeCounter(),
        client_pool=SimpleNamespace(for_module=lambda _id: client),
    )
    return WorkModuleEngine(_manifest(), ctx, db_engine=memory_engine), ctx, requests


def _events_json(*events: dict) -> str:
    return "<json>" + json.dumps({"events": list(events)}) + "</json>"


def _tomorrow_noon() -> datetime:
    return (datetime.now().astimezone() + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)


def _seed(engine, title="Họp sprint", start=None, **kw):
    start = start or datetime.now(timezone.utc) + timedelta(minutes=14, seconds=50)
    ev = CalendarEvent(title=title, start=start, end=start + timedelta(minutes=30), **kw)
    engine.calendar_repo.replace_window(start - timedelta(hours=1), start + timedelta(hours=1), [ev], start)
    return ev


# ---------------- sync ----------------
async def test_valid_response_replaces_cache_and_sets_fetched_at(memory_engine):
    noon = _tomorrow_noon()
    reply = _events_json({"id": "a", "title": "Họp", "start": noon.isoformat(), "end": None, "location": None,
                          "meet_url": "https://meet.google.com/x", "all_day": False})
    engine, ctx, requests = _setup(memory_engine, [reply])
    assert await engine.calendar_sync.sync() is True
    rows = engine.calendar_repo.between(noon - timedelta(hours=1), noon + timedelta(hours=1))
    assert [r.title for r in rows] == ["Họp"] and rows[0].meet_url == "https://meet.google.com/x"
    assert ctx.kv.get("work.calendar_fetched_at") and engine.calendar_sync.last_ok is True
    prompt = requests[0]["messages"][-1]["content"]
    assert prompt.startswith("[TED_CALENDAR_REQUEST] from=") and " to=" in prompt and " tz=" in prompt
    assert "{{" not in prompt


async def test_error_response_keeps_cache_and_shows_warning(memory_engine):
    engine, ctx, requests = _setup(memory_engine, ['<json>{"error": "calendar unavailable: no auth"}</json>'])
    _seed(engine, start=_tomorrow_noon())
    assert await engine.calendar_sync.sync() is False
    assert len(engine.today_rows()) + len(engine.calendar_repo.between(
        datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=3))) >= 1
    assert engine.calendar_status_text().startswith("⚠️")
    assert len(requests) == 1  # lỗi nghiệp vụ không retry


async def test_garbage_twice_keeps_cache(memory_engine):
    engine, _ctx, requests = _setup(memory_engine, ["xin lỗi, không biết"])
    noon = _tomorrow_noon()
    _seed(engine, title="Giữ lại", start=noon)
    assert await engine.calendar_sync.sync() is False
    assert len(requests) == 2
    assert [r.title for r in engine.calendar_repo.between(noon - timedelta(hours=1), noon + timedelta(hours=1))] == ["Giữ lại"]


async def test_sync_skipped_while_in_flight(memory_engine):
    engine, _ctx, requests = _setup(memory_engine, [_events_json()])
    engine.calendar_sync._in_flight = True
    assert await engine.calendar_sync.sync() is False and requests == []


async def test_hermes_offline_keeps_cache(memory_engine):
    engine, ctx, _ = _setup(memory_engine, ["x"])
    down = HermesBrainClient(
        HermesConnection(id="work", name="W", base_url="http://hermes.test/v1", api_key="k"),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503, json={"error": "down"}))))
    ctx.client_pool = SimpleNamespace(for_module=lambda _id: down)
    noon = _tomorrow_noon()
    _seed(engine, start=noon)
    assert await engine.calendar_sync.sync() is False
    assert len(engine.calendar_repo.between(noon - timedelta(hours=1), noon + timedelta(hours=1))) == 1


# ---------------- reminders (không cần mạng) ----------------
def _service(engine):
    from src.engines.work.meeting_reminder_service import MeetingReminderService
    return MeetingReminderService(engine.ctx, engine.calendar_repo, [15, 5])


def test_reminder_fires_once_with_chime_bubble_and_survives_restart(memory_engine):
    engine, ctx, _ = _setup(memory_engine, ["x"])
    _seed(engine, title="Họp [TED_SYNC_PLAN] sprint", meet_url="https://meet.google.com/abc")
    service = _service(engine)
    assert service.tick() == 1
    text = ctx.bubble.current_text()
    assert text.startswith("⏰ 15 phút nữa: Họp") and "TED_SYNC_PLAN" not in text
    assert ctx.bubble._buttons.count() == 1 and ctx.audio.plays == 1
    assert service.tick() == 0
    assert _service(engine).tick() == 0  # khởi động lại app: không bắn lại
    assert ctx.audio.plays == 1


def test_reminder_started_at_t_minus_3_fires_only_once(memory_engine):
    engine, ctx, _ = _setup(memory_engine, ["x"])
    _seed(engine, start=datetime.now(timezone.utc) + timedelta(minutes=3))
    service = _service(engine)
    assert service.tick() == 1 and "3 phút nữa" in ctx.bubble.current_text()
    assert service.tick() == 0


def test_all_day_event_never_reminds(memory_engine):
    engine, ctx, _ = _setup(memory_engine, ["x"])
    start = datetime.now(timezone.utc) + timedelta(minutes=10)
    ev = CalendarEvent(title="Nghỉ", start=start, all_day=True)
    engine.calendar_repo.replace_window(start - timedelta(hours=1), start + timedelta(hours=1), [ev], start)
    assert _service(engine).tick() == 0 and ctx.audio.plays == 0


def test_old_reminded_keys_are_pruned_on_start(memory_engine):
    engine, ctx, _ = _setup(memory_engine, ["x"])
    old = (datetime.now() - timedelta(days=4)).date().isoformat()
    ctx.kv.set_json(f"work.reminded:{old}", ["k|15"])
    _service(engine)
    assert ctx.kv.get_json(f"work.reminded:{old}") == []


# ---------------- engine + tab ----------------
def test_engine_start_stop_manages_timers(memory_engine):
    engine, _ctx, _ = _setup(memory_engine, ["x"])
    engine.start()
    assert engine._first_poll.isActive() and engine._poll_timer.isActive()
    assert engine._poll_timer.interval() == 30 * 60_000
    engine.stop()
    assert not engine._first_poll.isActive() and not engine._poll_timer.isActive()
    assert not engine._reminders._timer.isActive()


def test_calendar_action_lists_remaining_events_only(memory_engine):
    engine, ctx, _ = _setup(memory_engine, ["x"])
    _seed(engine, title="Họp tương lai")
    engine.handle_action("calendar")
    assert "Họp tương lai" in ctx.bubble.current_text()


def test_tab_shows_stale_warning_and_all_day_label(memory_engine):
    engine, _ctx, _ = _setup(memory_engine, ["x"])
    start = datetime.now(timezone.utc)
    ev = CalendarEvent(title="Nghỉ lễ", start=start, all_day=True)
    engine.calendar_repo.replace_window(start - timedelta(days=1), start + timedelta(days=1), [ev], start)
    engine.calendar_sync.last_ok = False
    tab = engine.build_dashboard_tab()
    assert tab.calendar_status.text().startswith("⚠️")
    assert tab.calendar_list.item(0).text() == "Cả ngày  Nghỉ lễ"
