import re
from typing import Optional

MOOD_TAG_RE = re.compile(r"^\s*\[MOOD:([A-Z_]+)\]\s*")

# Đợi tối đa ngần này ký tự trước khi kết luận câu trả lời không có thẻ [MOOD:X]
_MAX_TAG_PROBE_CHARS = 28


class MoodTagStreamParser:
    """
    Tách thẻ cảm xúc `[MOOD:X]` ở đầu luồng stream của Hermes.
    feed(delta) → (mood | None, text_to_show); finish() xả phần đệm còn lại.
    """

    def __init__(self):
        self._buffer = ""
        self._parsed = False

    def feed(self, delta: str) -> tuple[Optional[str], str]:
        if self._parsed:
            return None, delta
        self._buffer += delta
        if "]" in self._buffer or len(self._buffer) > _MAX_TAG_PROBE_CHARS:
            return self._flush()
        return None, ""

    def finish(self) -> tuple[Optional[str], str]:
        if self._parsed or not self._buffer:
            return None, ""
        return self._flush()

    def _flush(self) -> tuple[Optional[str], str]:
        self._parsed = True
        buffer, self._buffer = self._buffer, ""
        match = MOOD_TAG_RE.match(buffer)
        if match:
            return match.group(1), buffer[match.end():]
        return None, buffer
