"""
request_json chạy trên AsyncOpenAI thật, chỉ thay tầng mạng bằng httpx.MockTransport
để đếm chính xác số HTTP call.
"""

import json

import httpx
import pytest
from pydantic import BaseModel

from src.bridge.hermes_client import HermesBrainClient, sanitize_for_history
from src.bridge.hermes_json_contract_request import extract_json_block, request_json
from src.bridge.hermes_mood_tag_stream_parser import MoodTagStreamParser
from src.core.connection_registry_and_settings_migration import HermesConnection


class Briefing(BaseModel):
    summary: str
    count: int


def _completion(content: str) -> dict:
    return {
        "id": "cmpl-1", "object": "chat.completion", "created": 0, "model": "hermes-agent",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
    }


def _client_with(replies: list, status: int = 200):
    """replies: chuỗi content trả lần lượt; phần tử Exception → ném ra như lỗi mạng."""
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content) if request.content else {})  # GET /models không có body
        reply = replies[min(len(calls) - 1, len(replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "denied"}})
        return httpx.Response(200, json=_completion(reply))

    conn = HermesConnection(id="test", name="Test", base_url="http://hermes.test/v1", api_key="sk-secret")
    client = HermesBrainClient(conn, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return client, calls


GOOD = '{"summary": "ok", "count": 2}'


@pytest.mark.parametrize("reply", [
    f"Đây là kết quả <json>{GOOD}</json> nhé",
    f"```json\n{GOOD}\n```",
    f"[MOOD:CHEER] {GOOD}",
])
async def test_tagged_fenced_and_bare_json_are_parsed(reply):
    client, calls = _client_with([reply])
    result = await request_json(client, "brief", Briefing)
    assert result == Briefing(summary="ok", count=2)
    assert len(calls) == 1


async def test_garbage_then_valid_retries_once_with_error_hint():
    client, calls = _client_with(["không có json", f"<json>{GOOD}</json>"])
    result = await request_json(client, "brief", Briefing)
    assert result is not None and result.count == 2
    assert len(calls) == 2
    assert "[TED_JSON_ERROR]" in calls[1]["messages"][-1]["content"]


async def test_persistent_garbage_returns_none_after_exactly_two_calls():
    client, calls = _client_with(['{"summary": "thiếu count"}'])
    assert await request_json(client, "brief", Briefing) is None
    assert len(calls) == 2


async def test_error_payload_returns_none_without_retry():
    client, calls = _client_with(['<json>{"error": "no calendar"}</json>'])
    assert await request_json(client, "brief", Briefing) is None
    assert len(calls) == 1


async def test_offline_returns_none_without_retry():
    client, calls = _client_with([httpx.ConnectError("refused")])
    assert await request_json(client, "brief", Briefing) is None
    assert len(calls) == 1


async def test_complete_text_does_not_touch_chat_history():
    client, _ = _client_with([GOOD])
    before = list(client.history)
    await request_json(client, "brief", Briefing, system="sys")
    assert client.history == before


async def test_ping_reports_wrong_api_key_without_leaking_it():
    client, _ = _client_with([GOOD], status=401)
    ok, message = await client.ping()
    assert not ok
    assert "API key" in message and "sk-secret" not in message


def test_extract_json_block_raises_when_no_json():
    with pytest.raises(ValueError):
        extract_json_block("xin chào")


def test_sanitize_for_history_strips_protocol_tags_and_json_blocks():
    text = "[TED_SYNC_PLAN] cập nhật <json>{\"a\": 1}</json> xong [TED_STATE: status=IDLE]"
    assert sanitize_for_history(text) == "cập nhật  xong"
    assert sanitize_for_history("[TED_ONBOARDING]") == ""


def test_mood_parser_splits_tag_across_chunks():
    parser = MoodTagStreamParser()
    assert parser.feed("[MOOD:CH") == (None, "")
    assert parser.feed("EER] Chào") == ("CHEER", "Chào")
    assert parser.feed(" bạn") == (None, " bạn")
    assert parser.finish() == (None, "")


def test_mood_parser_without_tag_flushes_on_finish():
    parser = MoodTagStreamParser()
    assert parser.feed("Hi") == (None, "")
    assert parser.finish() == (None, "Hi")
