"""
stream_chat: lịch sử chat riêng cho từng kết nối, lọc thẻ giao thức/khối <json> trước khi lưu,
và fallback khi Hermes offline. Chạy trên AsyncOpenAI thật, SSE trả qua httpx.MockTransport.
"""

import json

import httpx

from src.bridge.hermes_client import SYSTEM_FALLBACK_PROMPT, HermesBrainClient
from src.core.connection_registry_and_settings_migration import HermesConnection

CTX = {"status": "DEEP_WORK_RUNNING", "task": "viết báo cáo", "remaining_mins": 10}


def _sse(pieces: list[str]) -> httpx.Response:
    body = ""
    for piece in pieces:
        chunk = {
            "id": "c", "object": "chat.completion.chunk", "created": 0, "model": "hermes-agent",
            "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
        }
        body += f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
    body += "data: [DONE]\n\n"
    return httpx.Response(200, content=body.encode("utf-8"), headers={"content-type": "text/event-stream"})


def _client(conn_id: str, replies: list[list[str]], sent: list[dict]) -> HermesBrainClient:
    """replies: mỗi phần tử là danh sách delta cho một lượt stream; sent ghi lại body mỗi request."""
    queue = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return _sse(queue.pop(0))

    conn = HermesConnection(id=conn_id, name=f"Conn {conn_id}", base_url="http://hermes.test/v1", api_key="k")
    return HermesBrainClient(conn, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def _chat(client: HermesBrainClient, message: str) -> tuple[list[str], list[str]]:
    moods: list[str] = []
    tokens: list[str] = []
    await client.stream_chat(message, CTX, moods.append, tokens.append)
    return moods, tokens


async def test_protocol_only_message_is_sent_but_not_stored_in_history():
    sent: list[dict] = []
    client = _client("local", [["[MOOD:FOCUS] ", "Giữ nhịp nhé"]], sent)
    await _chat(client, "[TED_SYNC_PLAN]")

    assert sent[0]["messages"][-1]["content"].startswith("[TED_STATE:")  # Hermes vẫn nhận ngữ cảnh
    assert client.history == [{"role": "system", "content": SYSTEM_FALLBACK_PROMPT}]


async def test_mood_is_emitted_and_history_keeps_only_clean_text():
    sent: list[dict] = []
    client = _client("local", [["[MOOD:CHEER] ", "Xong ", "rồi"]], sent)
    user = 'Ghi nhận giúp mình <json>{"a": 1}</json> hôm nay [TED_STATE: status=X]'
    moods, tokens = await _chat(client, user)

    assert moods == ["IDLE", "CHEER"]   # IDLE trong lúc chờ, rồi mood do Hermes gửi
    assert "".join(tokens) == "Xong rồi"
    user_turn, assistant_turn = client.history[-2], client.history[-1]
    assert user_turn["role"] == "user" and "<json>" not in user_turn["content"] and "[TED_" not in user_turn["content"]
    assert "Ghi nhận giúp mình" in user_turn["content"]
    assert assistant_turn == {"role": "assistant", "content": "Xong rồi"}


async def test_avatar_idles_while_waiting_then_resumes_previous_mood_without_mood_tag():
    client = _client("local", [["Không có thẻ mood"], ["[MOOD:CHEER] ", "Có thẻ"]], [])
    moods: list[str] = []
    await client.stream_chat("hỏi 1", CTX, moods.append, lambda _t: None, resume_mood="FOCUS")
    assert moods == ["IDLE", "FOCUS"]

    moods.clear()
    await client.stream_chat("hỏi 2", CTX, moods.append, lambda _t: None, resume_mood="FOCUS")
    assert moods == ["IDLE", "CHEER"]   # Hermes đã đặt mood → không ghi đè bằng mood cũ


async def test_chat_histories_are_isolated_per_connection():
    work_sent: list[dict] = []
    tutor_sent: list[dict] = []
    work = _client("work", [["[MOOD:IDLE] ", "việc A"], ["[MOOD:IDLE] ", "việc A tiếp"]], work_sent)
    tutor = _client("tutor", [["[MOOD:IDLE] ", "bài học B"]], tutor_sent)

    await _chat(work, "công việc công ty")
    await _chat(tutor, "bài học tiếng Anh")
    await _chat(work, "tiếp tục việc")

    assert len(tutor.history) == 3  # system + 1 lượt của chính nó
    # Dùng cụm định danh riêng (system prompt đã chứa chữ "công việc")
    assert all("công việc công ty" not in m["content"] for m in tutor.history)
    assert "công việc công ty" not in json.dumps(tutor_sent[0]["messages"], ensure_ascii=False)
    work_second_request = json.dumps(work_sent[1]["messages"], ensure_ascii=False)
    assert "bài học tiếng Anh" not in work_second_request
    assert "công việc công ty" in work_second_request


async def test_offline_hermes_returns_fallback_without_touching_history():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    conn = HermesConnection(id="vps", name="Hermes VPS", base_url="http://hermes.test/v1", api_key="secret-key")
    client = HermesBrainClient(conn, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    moods, tokens = await _chat(client, "xin chào")

    assert moods == ["IDLE", "GENTLE_NUDGE"]
    assert "Hermes VPS" in tokens[0]
    assert "secret-key" not in tokens[0]
    assert len(client.history) == 1
