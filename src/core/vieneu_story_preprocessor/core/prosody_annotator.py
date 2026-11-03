"""Tầng 3 — Prosody & Pause Engine: cắt lượt nói thành Segment và tính thời gian nghỉ theo ma trận P-01..P-14 (spec §4.2).

Ngắt cứng = ranh giới Segment + `pause_after` (giây) — engine chèn PCM im lặng; ngắt mềm = dấu "..." / "," trong văn bản.
Ngắt giữa câu: cặp gạch ngang (P-08), gạch ngang cuối câu (P-09), dấu phẩy lấy hơi trong câu siêu dài (P-10),
"..." trước chữ thường, trích dẫn có danh từ dẫn (Embedded Quote Guard).
"""

import re
from dataclasses import dataclass, field

from src.core.vieneu_story_preprocessor.core.config_loader import load_config
from src.core.vieneu_story_preprocessor.core.dialogue_parser import Utterance, split_sentences, word_count

_MID_ELLIPSIS_RE = re.compile(r"(?<=\.\.\.)\s+(?=[^\W\d_])")


@dataclass
class Segment:
    text: str
    role: str = "narration"
    speaker: str = "Narrator"
    speed: float = 1.0
    emotion: str = ""          # [cười] / [thở dài]...: chỉ xuất ở exporter, KHÔNG gửi model (VieNeu đọc thẻ thành tiếng)
    pause_before: float = 0.0
    pause_after: float = 0.0
    paragraph: int = 0


@dataclass
class _Sentence:
    utt: Utterance
    pieces: list[tuple[str, float]] = field(default_factory=list)   # (văn bản, nghỉ sau) — mẩu cuối nghỉ theo câu
    words: int = 0
    countdown_step: int = -1


def effective_pauses(segments: list[Segment]) -> list[float]:
    """Khoảng lặng thật giữa segment i và i+1 = max(nghỉ sau i, nghỉ trước i+1); sau segment cuối = 0."""
    return [max(s.pause_after, segments[i + 1].pause_before) if i + 1 < len(segments) else 0.0
            for i, s in enumerate(segments)]


def _split_dashes(sentence: str, rules: dict) -> list[tuple[str, float]]:
    parts = [p.strip(" ,;") for p in sentence.split(" — ")]
    parts = [p for p in parts if p]
    if len(parts) == 1:
        return [(parts[0], 0.0)]
    if len(parts) == 2:   # P-09: A — B.
        return [(parts[0] + "...", rules["dash_tail"]), (parts[1], 0.0)]
    pair = rules["dash_pair"]   # P-08: A — B — C
    return [(p + "...", pair[min(i, len(pair) - 1)]) for i, p in enumerate(parts[:-1])] + [(parts[-1], 0.0)]


def _split_breath(text: str, rules: dict) -> list[tuple[str, float]]:
    """P-10: vế trước dấu phẩy ≥ 18 từ VÀ (theo sau là từ nối hoặc phần còn lại ≥ 8 từ) → ngắt lấy hơi."""
    words = rules["words"]
    connectors = tuple(rules["breath_connectors"])
    clauses = text.split(", ")
    out: list[tuple[str, float]] = []
    current = clauses[0]
    for i, clause in enumerate(clauses[1:], start=1):
        rest = ", ".join(clauses[i:])
        low = clause.casefold()
        if word_count(current) >= words["breath_clause_min"] and (
                any(low == c or low.startswith(c + " ") for c in connectors) or word_count(rest) >= words["breath_rest_min"]):
            out.append((current + ",", rules["breath_comma"]))
            current = clause
        else:
            current += ", " + clause
    out.append((current, 0.0))
    return out


def _split_sentence(sentence: str, rules: dict) -> list[tuple[str, float]]:
    pieces: list[tuple[str, float]] = []
    chunks = _MID_ELLIPSIS_RE.split(sentence)
    for ci, chunk in enumerate(chunks):
        for part, dash_pause in _split_dashes(chunk, rules):
            breath = _split_breath(part, rules)
            pieces.extend(breath[:-1])
            pieces.append((breath[-1][0], dash_pause))
        if ci + 1 < len(chunks):
            pieces[-1] = (pieces[-1][0], rules["ellipsis_mid"])
    return pieces


def _mark_countdowns(sentences: list[_Sentence], rules: dict) -> None:
    """P-05: chuỗi ≥ 3 câu lời dẫn ngắn liên tiếp trong cùng đoạn, có từ chỉ thời gian / im lặng → nghỉ tăng tiến."""
    words = rules["words"]
    time_words = tuple(rules["countdown_words"])
    run: list[_Sentence] = []

    def close() -> None:
        if len(run) >= words["countdown_run"] and any(
                any(t in s.pieces[0][0].casefold() for t in time_words) for s in run):
            for step, s in enumerate(run):
                s.countdown_step = step
        run.clear()

    for s in sentences:
        short = (s.utt.role == "narration" and len(s.pieces) == 1 and s.words <= words["countdown_max"]
                 and s.pieces[0][0].endswith("."))
        if short and run and run[-1].utt.paragraph != s.utt.paragraph:
            close()
        if short:
            run.append(s)
        else:
            close()
    close()


def _sentence_pause(s: _Sentence, first: bool, last: bool, rules: dict) -> float:
    words = rules["words"]
    text = s.pieces[-1][0].rstrip('"')
    if s.countdown_step >= 0:
        steps = rules["countdown"]
        return steps[min(s.countdown_step, len(steps) - 1)]
    if text.endswith(("?", "!")):
        return rules["question_exclaim"]
    if s.words <= words["emphatic_max"] and (first or last):
        return rules["emphatic_short"]
    if s.words >= words["epic_min"]:
        return rules["epic"]
    if s.words >= words["standard_min"]:
        return rules["standard"]
    return rules["short_action"]


def annotate(utterances: list[Utterance], map_text=lambda t: t) -> list[Segment]:
    rules = load_config("pause_rules.json")
    tones = {t["name"]: t for t in load_config("tone_rules.json") or []}
    sentences: list[_Sentence] = []
    scene_after: set[int] = set()   # chỉ số câu đứng ngay trước dấu đổi cảnh
    for u in utterances:
        if u.role == "scene_break":
            if sentences:
                scene_after.add(len(sentences) - 1)
            continue
        for text in split_sentences(u.text):
            sentences.append(_Sentence(u, _split_sentence(text, rules), word_count(text)))
    _mark_countdowns(sentences, rules)

    segments: list[Segment] = []
    for i, s in enumerate(sentences):
        u = s.utt
        prev_s = sentences[i - 1] if i else None
        next_s = sentences[i + 1] if i + 1 < len(sentences) else None
        para_first = prev_s is None or prev_s.utt.paragraph != u.paragraph
        para_last = next_s is None or next_s.utt.paragraph != u.paragraph
        utt_last = next_s is None or next_s.utt is not u
        pause = _sentence_pause(s, para_first, para_last, rules)
        tone = tones.get(u.tone, {})
        if "end_pause" in tone:
            pause = tone["end_pause"]
        if utt_last and u.pause_after is not None:
            pause = u.pause_after
        if utt_last and next_s is not None and next_s.utt.paragraph == u.paragraph and next_s.utt.role != u.role:
            switch = rules["inner_voice"] if "inner_voice" in (u.role, next_s.utt.role) else rules["dialogue_switch"]
            pause = max(pause, switch)   # P-11 / P-12
        if para_last and next_s is not None and not s.pieces[-1][0].endswith(":"):
            both_items = u.paragraph_kind == next_s.utt.paragraph_kind == "list_item"
            pause = max(pause, rules["list_item"] if both_items else rules["paragraph"])   # P-13
        if i in scene_after:
            pause = max(pause, rules["scene_break"])   # P-14

        role = "narration_countdown" if s.countdown_step >= 0 else u.role
        speed = tone.get("speed", rules["role_speed"].get(role, 1.0))
        utt_first = prev_s is None or prev_s.utt is not u   # nghỉ-trước & thẻ cảm xúc chỉ gắn vào đầu lượt nói
        for pi, (text, piece_pause) in enumerate(s.pieces):
            if role == "narration_countdown" and text.endswith(".") and not text.endswith("..."):
                text = text[:-1] + "..."
            head = utt_first and pi == 0
            segments.append(Segment(
                map_text(text), role, u.speaker, speed, tone.get("emotion", "") if head else "",
                u.pause_before if head else 0.0, pause if pi == len(s.pieces) - 1 else piece_pause, u.paragraph))
    if segments:
        segments[-1].pause_after = 0.0
    return [seg for seg in segments if seg.text.strip()]
