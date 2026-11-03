"""Tầng 5 — Chế độ 1: kịch bản phẳng gắn thẻ cho VieNeu Studio / sách nói (spec §5.2).

    Người dẫn: Câu một. [0.35] Câu hai. [1.0]

    Nhân vật: [cười] Câu thoại. [0.65]
"""

from src.core.vieneu_story_preprocessor.core.dialogue_parser import NARRATOR
from src.core.vieneu_story_preprocessor.core.prosody_annotator import Segment, effective_pauses

SPEAKER_LABELS = {NARRATOR: "Người dẫn"}


def format_pause(seconds: float) -> str:
    text = f"{seconds:.2f}".rstrip("0")
    return f"[{text}0]" if text.endswith(".") else f"[{text}]"


def to_studio_script(segments: list[Segment]) -> str:
    """Gộp các segment liền nhau cùng đoạn & cùng người nói thành một dòng; khác người nói / đoạn → dòng mới."""
    blocks: list[str] = []
    key = None
    for seg, pause in zip(segments, effective_pauses(segments)):
        piece = (f"[{seg.emotion}] " if seg.emotion else "") + seg.text + (f" {format_pause(pause)}" if pause else "")
        if (seg.paragraph, seg.speaker) == key:
            blocks[-1] += " " + piece
        else:
            blocks.append(f"{SPEAKER_LABELS.get(seg.speaker, seg.speaker)}: {piece}")
            key = (seg.paragraph, seg.speaker)
    return "\n\n".join(blocks) + ("\n" if blocks else "")
