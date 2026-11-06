"""Refill chạy trên AsyncOpenAI thật; chỉ thay tầng mạng bằng httpx.MockTransport để đếm số HTTP call."""

import asyncio
import json
import re
from types import SimpleNamespace

import httpx

from src.bridge.hermes_client import HermesBrainClient
from src.core.connection_registry_and_settings_migration import HermesConnection
from src.engines.coach.quiz_batch_refill_service import refill_if_needed
from coach_test_support import MODULE, NOW, repos, seed

MODULE_OBJ = SimpleNamespace(id=MODULE, learner_id="con")


def _batch(n: int, start: int = 0, topic: str = "english.conditionals") -> str:
    items = [{"topic": topic, "type": "short", "question": f"New {start + i}", "answer": "a"} for i in range(n)]
    return "<json>" + json.dumps({"items": items}) + "</json>"


def _client(replies, delay: float = 0.0):
    calls: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        if delay:
            await asyncio.sleep(delay)
        content = replies[min(len(calls) - 1, len(replies) - 1)]
        return httpx.Response(200, json={
            "id": "c", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        })

    conn = HermesConnection(id="t", name="T", base_url="http://hermes.test/v1", api_key="k")
    return HermesBrainClient(conn, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))), calls


def _request_payload(call: dict) -> dict:
    text = call["messages"][-1]["content"]
    assert text.startswith("[TED_QUIZ_BATCH_REQUEST]")
    return json.loads(re.search(r"<json>(.*?)</json>", text, re.S).group(1))


async def test_below_threshold_makes_one_call_and_inserts_rows(memory_engine):
    items, _ = repos(memory_engine)
    seed(memory_engine, ["Old 1", "Old 2"])   # 2 chưa hỏi < 5
    client, calls = _client([_batch(4)])
    assert await refill_if_needed(MODULE_OBJ, items, client, NOW) == 4
    assert len(calls) == 1 and items.unseen_count(MODULE) == 6
    request = _request_payload(calls[0])
    assert request["learner"] == "con" and request["count"] == 10 and request["topic"] is None
    assert request["types"] is None and set(request["recent_questions"]) == {"Old 1", "Old 2"}


async def test_enough_unseen_makes_no_call(memory_engine):
    items, _ = repos(memory_engine)
    seed(memory_engine, [f"Q{i}" for i in range(5)])
    client, calls = _client([_batch(4)])
    assert await refill_if_needed(MODULE_OBJ, items, client, NOW) == 0 and calls == []


async def test_concurrent_double_call_sends_single_request(memory_engine):
    items, _ = repos(memory_engine)
    client, calls = _client([_batch(3)], delay=0.05)
    results = await asyncio.gather(*[refill_if_needed(MODULE_OBJ, items, client, NOW) for _ in range(2)])
    assert sorted(results) == [0, 3] and len(calls) == 1


async def test_in_flight_flag_released_after_failure(memory_engine):
    items, _ = repos(memory_engine)
    client, calls = _client(["không phải json"])
    assert await refill_if_needed(MODULE_OBJ, items, client, NOW) == 0
    assert len(calls) == 2   # request_json: 1 lần + 1 retry
    client2, calls2 = _client([_batch(2)])
    assert await refill_if_needed(MODULE_OBJ, items, client2, NOW) == 2 and len(calls2) == 1


async def test_garbage_twice_inserts_nothing(memory_engine):
    items, _ = repos(memory_engine)
    client, calls = _client(['<json>{"items": []}</json>'])
    assert await refill_if_needed(MODULE_OBJ, items, client, NOW) == 0
    assert len(calls) == 2 and items.unseen_count(MODULE) == 0


async def test_offline_returns_zero_without_retry(memory_engine):
    items, _ = repos(memory_engine)

    def boom(request):
        raise httpx.ConnectError("refused")

    conn = HermesConnection(id="t", name="T", base_url="http://hermes.test/v1", api_key="k")
    client = HermesBrainClient(conn, http_client=httpx.AsyncClient(transport=httpx.MockTransport(boom)))
    assert await refill_if_needed(MODULE_OBJ, items, client, NOW) == 0


async def test_topic_threshold_is_three_and_topic_is_sent(memory_engine):
    items, _ = repos(memory_engine)
    seed(memory_engine, [f"Other {i}" for i in range(9)], topic="math.inequalities")   # nhiều câu chủ đề khác
    seed(memory_engine, ["E1", "E2"], topic="english.conditionals")
    client, calls = _client([_batch(5, topic="english.conditionals")])
    assert await refill_if_needed(MODULE_OBJ, items, client, NOW, topic="english.conditionals") == 5
    assert _request_payload(calls[0])["topic"] == "english.conditionals"
    client2, calls2 = _client([_batch(1)])
    assert await refill_if_needed(MODULE_OBJ, items, client2, NOW, topic="english.conditionals") == 0   # 7 ≥ 3
    assert calls2 == []


async def test_duplicate_questions_from_hermes_are_not_inserted_twice(memory_engine):
    items, _ = repos(memory_engine)
    seed(memory_engine, ["New 0"])
    client, _ = _client([_batch(3)])   # "New 0" trùng câu đã có
    assert await refill_if_needed(MODULE_OBJ, items, client, NOW) == 2


async def test_step_types_request_sends_types_and_count(memory_engine):
    items, _ = repos(memory_engine)
    step = '<json>{"items":[{"topic":"math.x","type":"step","question":"Prove","hints":["h"],"answer":"sol"}]}</json>'
    client, calls = _client([step])
    assert await refill_if_needed(MODULE_OBJ, items, client, NOW, topic="math.x", types=["step"], count=1) == 1
    request = _request_payload(calls[0])
    assert request["types"] == ["step"] and request["count"] == 1
    assert await refill_if_needed(MODULE_OBJ, items, client, NOW, topic="math.x", types=["step"], count=1) == 0
    assert len(calls) == 1   # đã có 1 câu step chưa hỏi
