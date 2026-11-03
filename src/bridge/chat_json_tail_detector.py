"""Dò khối `<json>…</json>` ở cuối câu trả lời streaming (vd. `{"onboarding":"done"}`): ẩn khỏi khung chat và trả JSON.

Thuần hàm, không phụ thuộc Qt. Nguyên tắc (Red Team #10): chỉ giữ kín từ lúc thấy đủ thẻ mở `<json>` NGOÀI code fence;
chữ thường ("dùng thẻ <json> nhé", hay `<json>` trong ``` do model viết) vẫn hiển thị bình thường; JSON hỏng thì ẩn
nhưng trả None (không kích hoạt gì)."""

import json
import re
from typing import Optional

OPEN_TAG = "<json>"
FENCE = "```"
_BLOCK_RE = re.compile(r"<json>\s*(.*?)\s*</json>\s*", re.S)


class ChatJsonTailDetector:
    def __init__(self) -> None:
        self._pending = ""                 # đuôi có thể là đầu thẻ `<json>` → chưa hiển thị
        self._held: Optional[str] = None   # từ thẻ mở trở đi, đang giữ kín tới hết stream
        self._shown = ""                   # toàn bộ chữ đã hiển thị (để biết đang ở trong code fence hay không)

    def _in_fence(self) -> bool:
        return self._shown.count(FENCE) % 2 == 1

    def _emit(self, text: str) -> str:
        self._shown += text
        return text

    def feed(self, token: str) -> str:
        """Trả phần được phép hiển thị ngay; có thể rỗng khi đang giữ đuôi nghi là thẻ `<json>`."""
        if self._held is not None:
            self._held += token
            return ""
        text, self._pending, out = self._pending + token, "", ""
        while True:
            idx = text.find(OPEN_TAG)
            if idx == -1:
                break
            out += self._emit(text[:idx])
            if self._in_fence():           # `<json>` do model viết trong code fence → chữ thường
                out += self._emit(OPEN_TAG)
                text = text[idx + len(OPEN_TAG):]
                continue
            self._held = text[idx:]
            return out
        keep = next((n for n in range(min(len(OPEN_TAG) - 1, len(text)), 0, -1) if OPEN_TAG.startswith(text[-n:])), 0)
        self._pending = text[len(text) - keep:]
        return out + self._emit(text[:len(text) - keep])

    def finish(self) -> tuple[str, Optional[dict]]:
        """(chữ còn lại cần hiển thị, JSON object của khối cuối nếu hợp lệ). Gọi 1 lần khi stream kết thúc."""
        leftover, self._pending = self._pending, ""
        held, self._held = self._held, None
        if held is None:
            return leftover, None
        # Chỉ chấp nhận khối nằm ở CUỐI câu trả lời (sau </json> chỉ còn khoảng trắng). JSON giữa câu (vd. người học gõ
        # rồi model nhắc lại) → trả toàn bộ chữ đã giữ về khung chat, không kích hoạt handler.
        match = _BLOCK_RE.fullmatch(held)
        if match is not None and (OPEN_TAG in match.group(1) or "</json>" in match.group(1)):
            match = None   # nhiều khối <json> trong câu: khối đầu nằm giữa câu → không phải khối cuối
        if match is None:
            # Thẻ mở không có thẻ đóng (hoặc còn chữ sau thẻ đóng): trả lại cho người dùng, trừ khi là JSON cụt (ẩn)
            truncated = "</json>" not in held and held[len(OPEN_TAG):].lstrip().startswith("{")
            return (leftover if truncated else leftover + held), None
        try:
            data = json.loads(match.group(1))
        except ValueError:
            return leftover, None
        return leftover, data if isinstance(data, dict) else None
