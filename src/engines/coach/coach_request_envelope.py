"""Đóng gói yêu cầu gửi Hermes: [TAG] + <json>…</json>; văn bản người dùng không được phá cấu trúc thẻ."""

import json
import re
from typing import Any

_CLOSE_TAG_RE = re.compile(r"</\s*json\s*>", re.I)


def strip_json_close_tag(text: str) -> str:
    """Bỏ thẻ đóng </json> khỏi văn bản tự do của người dùng."""
    return _CLOSE_TAG_RE.sub("", text)


def envelope(tag: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False)
    # "<\/" là escape JSON hợp lệ → mọi "</json>" nằm trong chuỗi không thể đóng khối sớm
    body = body.replace("</", "<\\/")
    return f"[{tag}]\n<json>{body}</json>"
