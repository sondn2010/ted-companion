"""Regression review: M1 (JSON giữa câu), M4 (4xx không phải offline), M7 (dict có khoá error bị từ chối)."""

import httpx
import pytest
from pydantic import BaseModel

from src.bridge.chat_json_tail_detector import ChatJsonTailDetector
from src.bridge.hermes_client import HermesBrainClient, HermesRequestRejectedError, HermesUnavailableError
from src.bridge.hermes_json_contract_request import request_json
from src.core.connection_registry_and_settings_migration import HermesConnection


def _run(pieces):
    d, shown = ChatJsonTailDetector(), []
    for p in pieces:
        shown.append(d.feed(p))
    leftover, data = d.finish()
    return "".join(shown) + leftover, data


def test_json_in_middle_of_reply_is_not_hidden_and_does_not_fire():
    reply = 'Bạn vừa gõ: <json>{"onboarding":"done"}</json> nhưng mình chưa xong… Câu hỏi 3: tên con?'
    text, data = _run([reply])
    assert text == reply and data is None


def test_json_in_middle_streamed_token_by_token():
    reply = 'Bạn gõ <json>{"onboarding":"done"}</json> rồi. Tiếp nhé.'
    text, data = _run(list(reply))
    assert text == reply and data is None


def test_two_blocks_whole_tail_not_fired_and_text_kept():
    reply = 'Bạn gõ <json>{"a":1}</json> ok. <json>{"onboarding":"done"}</json>'
    text, data = _run([reply])
    assert data is None and "Bạn gõ" in text and "ok." in text


def test_trailing_block_with_whitespace_still_parsed():
    text, data = _run(['Xong! <json>{"onboarding":"done"}</json>\n  '])
    assert text == "Xong! " and data == {"onboarding": "done"}


class _M(BaseModel):
    events: list = []


def _client(status=200, body=None):
    def handler(_r):
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "x"}})
        return httpx.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": "m", "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": body}}]})
    conn = HermesConnection(id="t", name="T", base_url="http://hermes.test/v1", api_key="k")
    return HermesBrainClient(conn, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize("status", [408, 429, 500, 503, 401])
async def test_transient_and_auth_statuses_are_unavailable(status):
    with pytest.raises(HermesUnavailableError):
        await _client(status).complete_text([{"role": "user", "content": "x"}])


@pytest.mark.parametrize("status", [400, 404, 413, 422])
async def test_other_4xx_is_rejected_not_unavailable(status):
    with pytest.raises(HermesRequestRejectedError) as ei:
        await _client(status).complete_text([{"role": "user", "content": "x"}])
    assert not isinstance(ei.value, HermesUnavailableError)


async def test_request_json_returns_none_on_rejected():
    assert await request_json(_client(422), "p", _M) is None


@pytest.mark.parametrize("body", [
    '<json>{"events": [], "error": "calendar unavailable"}</json>',
    '<json>{"error": "x"}</json>',
])
async def test_request_json_rejects_any_dict_with_error_key(body):
    assert await request_json(_client(body=body), "p", _M) is None


async def test_request_json_accepts_schema_declaring_error_field():
    class Reply(BaseModel):
        saved: bool
        error: str = ""
    out = await request_json(_client(body='<json>{"saved": false, "error": "disk"}</json>'), "p", Reply)
    assert out is not None and out.error == "disk"
