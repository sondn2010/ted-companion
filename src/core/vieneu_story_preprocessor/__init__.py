"""Prosody & Script Preprocessor cho VieNeu-TTS (docs/tts-specs/tts-specs-v1.md) — thuần rule-based, nhẹ CPU.

    sanitizer → dialogue_parser → prosody_annotator → lexicon_mapper → exporters (Studio txt / JSON chunks)

VieNeu 3.8.3 KHÔNG hiểu thẻ [giây] / [cười] / <en> (đo thực tế: [3.0] không nghỉ dài hơn [0.5], thẻ còn bị đọc thành
~0.5 s tiếng lạ) → ngắt cứng trả về dạng `Segment.pause_after` để engine chèn PCM im lặng; thẻ chỉ có ở exporter Studio.
"""

import re

from src.core.vieneu_story_preprocessor.core.dialogue_parser import parse
from src.core.vieneu_story_preprocessor.core.lexicon_mapper import map_pronunciation, normalize_caps
from src.core.vieneu_story_preprocessor.core.prosody_annotator import Segment, annotate, effective_pauses
from src.core.vieneu_story_preprocessor.core.sanitizer import sanitize

__all__ = ["Segment", "effective_pauses", "preprocess"]

_VIETNAMESE_CHARS_RE = re.compile(r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]", re.I)


def preprocess(text: str) -> list[Segment]:
    """Văn bản thô (giữ xuống dòng) → các Segment đã điền ngắt nghỉ, tốc độ, cách đọc.
    Từ điển phát âm kiểu Việt chỉ áp cho văn bản tiếng Việt; văn bản tiếng Anh chỉ hạ chữ IN HOA."""
    vietnamese = bool(_VIETNAMESE_CHARS_RE.search(text or ""))
    return annotate(parse(sanitize(text)), map_pronunciation if vietnamese else normalize_caps)
