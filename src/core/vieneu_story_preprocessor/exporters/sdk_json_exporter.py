"""Tầng 5 — Chế độ 2: JSON chunks kèm speaker / speed / pause cho backend gọi `vieneu.infer()` từng khúc (spec §5.3)."""

from typing import Optional

from src.core.vieneu_story_preprocessor.core.prosody_annotator import Segment, effective_pauses


def to_json_chunks(segments: list[Segment], voices: Optional[dict[str, str]] = None, prefix: str = "") -> list[dict]:
    """`voices`: người nói → giọng preset (thiếu = ""). `chunk_id` = <prefix>p<đoạn>_s<thứ tự trong đoạn>."""
    voices = voices or {}
    chunks, counters = [], {}
    pauses = effective_pauses(segments)
    for seg, pause in zip(segments, pauses):
        counters[seg.paragraph] = counters.get(seg.paragraph, 0) + 1
        chunks.append({
            "chunk_id": f"{prefix}p{seg.paragraph + 1:02d}_s{counters[seg.paragraph]:02d}",
            "speaker": seg.speaker,
            "voice_preset": voices.get(seg.speaker, ""),
            "role_type": seg.role,
            "text": seg.text,
            "emotion": seg.emotion,
            "speed": seg.speed,
            "pause_before_sec": seg.pause_before,
            "pause_after_sec": pause,
        })
    return chunks
