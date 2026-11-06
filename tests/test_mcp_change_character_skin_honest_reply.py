"""MCP change_character_skin không được khẳng định "đã đổi": ứng dụng có thể từ chối nhân vật còn khóa."""
from src.bridge import ted_mcp_server as mcp_server


def test_reply_says_request_sent_and_mentions_locked_rejection(monkeypatch):
    sent = []
    monkeypatch.setattr(mcp_server, "_enqueue_ui_command", sent.append)
    reply = mcp_server.change_character_skin("CAT ")
    assert sent == [{"type": "change_character", "skin": "cat"}]
    assert "đã gửi yêu cầu" in reply.lower() and "khóa" in reply and "Đã đổi" not in reply


def test_invalid_skin_is_not_enqueued(monkeypatch):
    sent = []
    monkeypatch.setattr(mcp_server, "_enqueue_ui_command", sent.append)
    assert "không hợp lệ" in mcp_server.change_character_skin("khong-co")
    assert sent == []
