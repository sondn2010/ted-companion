"""Tầng 2 — Discourse & Dialogue Parser: tách đoạn thành lượt nói (Utterance) theo vai.

Vai: narration (lời dẫn) | dialogue (thoại trong ngoặc kép) | dialogue_shout (tiếng hô / gọi tên đứng riêng)
     | inner_voice (độc thoại nội tâm / thần giao cách cảm không ngoặc kép) | scene_break.
Quy tắc biên của spec §2: Telepathic Detector (2), Shout & Roll-Call (4), Split-Dialogue Linker (5), Embedded Quote Guard (6).
Ted chỉ dùng 1 giọng: vai / người nói chỉ quyết định ngắt nghỉ, tốc độ và nhãn ở exporter.
"""

import re
from dataclasses import dataclass
from typing import Optional

from src.core.vieneu_story_preprocessor.core.config_loader import load_config
from src.core.vieneu_story_preprocessor.core.lexicon_mapper import known_name_words
from src.core.vieneu_story_preprocessor.core.sanitizer import Paragraph

NARRATOR = "Narrator"
INNER_SPEAKER = "Nội tâm"
UNKNOWN_SPEAKER = "Nhân vật"

_QUOTE_RE = re.compile(r'"([^"]+)"')
_SENTENCE_GAP_RE = re.compile(r"(?<=[.!?:])\s+")
_WORD_RE = re.compile(r"[^\W_]+(?:['-][^\W_]+)*")
_SPEECH_VERBS = ("nói", "hỏi", "đáp", "thì thầm", "hét", "gào", "kêu", "reo", "hô", "cười", "thở dài", "lẩm bẩm",
                 "tiếp tục", "trả lời", "quát", "rít", "gọi")
_INNER_TRIGGERS = ("trong tâm trí", "trong đầu", "tự nhủ", "thần giao cách cảm", "trong suy nghĩ")
_EMBED_CUES = ("câu nói", "lời nói", "câu", "chữ", "cụm từ", "từ", "dòng chữ", "biệt danh", "khẩu hiệu")
_INNER_CUES = ("tôi", "ta", "con", "mình", "chà", "hừm", "ồ", "à", "đúng vậy", "ừ")
_THIRD_PERSON = ("cô", "cậu", "anh", "chị", "ông", "bà", "hắn", "nó", "họ", "chiếc nón", "giọng nói", "bé")
# Từ viết hoa đầu câu không phải tên người
_NOT_NAMES = set(_THIRD_PERSON) | {"rồi", "khi", "sau", "nhưng", "và", "thì", "lúc", "ngay", "một", "cả", "chiếc", "giọng",
                                    "người", "lão", "bà", "cô", "con", "này", "đó", "mọi"}

_EMBED_CUE_RE = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, _EMBED_CUES)) + r")$")
_SUBJECT_ALT = "|".join(map(re.escape, _THIRD_PERSON))
_VERB_ALT = "|".join(map(re.escape, _SPEECH_VERBS))
# "Rất thông minh, chiếc nón thì thầm." / "X, giọng nói tiếp tục, Y."
_INTERJECTED_TAG_RE = re.compile(
    rf"^(?P<head>.+?),\s*(?P<tag>(?:{_SUBJECT_ALT})\s[^,.!?]*?\b(?:{_VERB_ALT})\b[^,.!?]*)(?P<end>[,.!?])\s*(?P<tail>.*)$",
    re.I)


@dataclass
class Utterance:
    text: str
    role: str = "narration"
    speaker: str = NARRATOR
    tone: str = ""                        # tên nhóm sắc thái trong tone_rules.json
    pause_before: float = 0.0
    pause_after: Optional[float] = None   # None → tầng ngắt nghỉ tự tính theo câu
    paragraph: int = 0
    paragraph_kind: str = "text"


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def split_sentences(text: str) -> list[str]:
    """Tách ở . ! ? : + khoảng trắng; mẩu sau bắt đầu bằng chữ thường thì vẫn thuộc câu trước ("Hoặc ít nhất... con biết")."""
    out: list[str] = []
    for piece in _SENTENCE_GAP_RE.split(text.strip()):
        if not piece:
            continue
        if out and piece[0].islower():
            out[-1] = f"{out[-1]} {piece}"
        else:
            out.append(piece)
    return out


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def _starts_with(text: str, words) -> bool:
    low = text.casefold()
    return any(low == w or low.startswith(w + " ") or low.startswith(w + ",") for w in words)


def _tone_of(tag: str) -> str:
    low = tag.casefold()
    for rule in load_config("tone_rules.json") or []:
        if any(k in low for k in rule["keywords"]):
            return rule["name"]
    return ""


def _speaker_in(tag: str) -> str:
    names = []
    for word in _WORD_RE.findall(tag):
        if word[:1].isupper() and word.casefold() not in _NOT_NAMES:
            names.append(word)
        elif names:
            break
    return " ".join(names[:2])


def _is_tag(text: str) -> bool:
    first = split_sentences(text)[0] if text else ""
    low = first.casefold()
    return bool(first) and word_count(first) <= 10 and any(re.search(rf"\b{re.escape(v)}\b", low) for v in _SPEECH_VERBS)


def _ensure_end(text: str) -> str:
    text = text.strip()
    if text.endswith(","):
        return text[:-1] + "."
    return text if text.endswith((".", "!", "?", ":", ";")) else text + "."


def _shout_utterances(content: str, idx: int, rules: dict) -> list[Utterance]:
    """Tiếng hô / gọi tên đứng riêng: IN HOA → dạng thường, nghỉ chờ trước & sau; "Họ, Tên!" → "Họ..." [0.25] "Tên!"."""
    content = re.sub(r"[^\W\d_]+", lambda m: m.group(0).capitalize() if m.group(0).isupper() else m.group(0), content)
    parts = [p.strip() for p in content.split(",") if p.strip()]
    utts = [Utterance(p + "...", "dialogue_shout", UNKNOWN_SPEAKER, pause_after=rules["roll_call_comma"], paragraph=idx)
            for p in parts[:-1]]
    utts.append(Utterance(parts[-1], "dialogue_shout", UNKNOWN_SPEAKER, pause_after=rules["shout_after"], paragraph=idx))
    utts[0].pause_before = rules["shout_before"]
    return utts


def _parse_quoted(text: str, idx: int, rules: dict) -> list[Utterance]:
    utts: list[Utterance] = []
    buf = ""
    continues_sentence = False   # phần lời dẫn tiếp nối sau trích dẫn giữa câu: không viết hoa lại

    def flush(pause_after: Optional[float] = None) -> None:
        nonlocal buf, continues_sentence
        narration = buf.strip().lstrip("—,; ").strip()
        if narration:
            utts.append(Utterance(narration if continues_sentence else _capitalize(narration),
                                  pause_after=pause_after, paragraph=idx))
        buf, continues_sentence = "", False

    pos = 0
    for m in _QUOTE_RE.finditer(text):
        before, content = text[pos:m.start()], m.group(1).strip()
        pos = m.end()
        sentence_before = (buf + before).strip()
        mid_sentence = bool(sentence_before) and not sentence_before.endswith((".", "!", "?", ":", "—"))
        if mid_sentence and not content.endswith((".", "!", "?", ",", "...")):
            # Embedded Quote Guard: trích dẫn giữa câu vẫn là lời dẫn
            if _EMBED_CUE_RE.search(sentence_before.casefold()):
                buf += before.rstrip() + "..."
                flush(rules["embedded_quote"][0])
                utts.append(Utterance(content, pause_after=rules["embedded_quote"][1], paragraph=idx))
                continues_sentence = True
            else:
                buf += before + content
            continue
        buf += before
        flush()
        utts.append(Utterance(_ensure_end(content), "dialogue", UNKNOWN_SPEAKER, paragraph=idx))
    buf += text[pos:]
    flush()

    dialogues = [u for u in utts if u.role == "dialogue"]
    if len(utts) == 1 and len(dialogues) == 1 and word_count(dialogues[0].text) <= 3 and dialogues[0].text.endswith("!"):
        return _shout_utterances(dialogues[0].text, idx, rules)
    return utts


def _link_speakers(utts: list[Utterance], previous: Optional[Utterance]) -> None:
    """Gán người nói & sắc thái cho thoại từ lời dẫn kề bên; thoại không có lời dẫn riêng thừa hưởng người nói trước đó
    trong cùng đoạn (Split-Dialogue Linker)."""
    last_speaker = ""
    for i, u in enumerate(utts):
        if u.role not in ("dialogue", "dialogue_shout"):
            continue
        after = utts[i + 1] if i + 1 < len(utts) and utts[i + 1].role == "narration" else None
        before = utts[i - 1] if i > 0 else previous
        tag = ""
        if after is not None and _is_tag(after.text):
            tag = split_sentences(after.text)[0]
        elif before is not None and before.role == "narration" and before.text.endswith(":"):
            tag = split_sentences(before.text)[-1]
        u.speaker = (_speaker_in(tag) if tag else "") or last_speaker or u.speaker
        u.tone = _tone_of(tag) if tag else u.tone
        last_speaker = u.speaker


def _parse_inner(text: str, idx: int) -> tuple[list[Utterance], bool]:
    """Đoạn độc thoại nội tâm: tách câu dẫn ngôi thứ 3 (tên riêng / đại từ / ", chiếc nón thì thầm.") ra khỏi giọng nội tâm.
    Trả (lượt nói, đoạn có dấu hiệu nội tâm → đoạn sau vẫn có thể là nội tâm)."""
    names = known_name_words()
    pieces: list[tuple[str, str]] = []   # (role, câu)
    cue = False
    queue = split_sentences(text)
    while queue:
        sentence = queue.pop(0)
        m = _INTERJECTED_TAG_RE.match(sentence)
        if m:
            cue = True
            pieces.append(("inner_voice", m.group("head").strip() + "."))
            pieces.append(("narration", _capitalize(m.group("tag").strip()) + "."))
            if m.group("tail").strip():
                queue.insert(0, _capitalize(m.group("tail").strip()))
            continue
        first = (_WORD_RE.findall(sentence) or [""])[0].casefold()
        if _starts_with(sentence, _THIRD_PERSON) or first in names:
            pieces.append(("narration", sentence))
        else:
            cue = cue or _starts_with(sentence, _INNER_CUES)
            pieces.append(("inner_voice", sentence))
    utts: list[Utterance] = []
    for role, sentence in pieces:
        if role == "inner_voice":
            sentence = _soften_short_commas(sentence)
        if utts and utts[-1].role == role:
            utts[-1].text += " " + sentence
        else:
            utts.append(Utterance(sentence, role, INNER_SPEAKER if role == "inner_voice" else NARRATOR,
                                  tone="inner" if role == "inner_voice" else "", paragraph=idx))
    return utts, cue


def _soften_short_commas(sentence: str) -> str:
    """Nội tâm: dấu phẩy sau vế ngắn (≤ 3 từ) → "..." (ngân, ngập ngừng)."""
    parts = sentence.split(", ")
    out = parts[0]
    for part in parts[1:]:
        out += ("... " if word_count(out.rsplit("...", 1)[-1]) <= 3 else ", ") + part
    return out


def parse(paragraphs: list[Paragraph]) -> list[Utterance]:
    rules = load_config("pause_rules.json")
    out: list[Utterance] = []
    inner = False
    for idx, p in enumerate(paragraphs):
        if p.kind == "scene_break":
            out.append(Utterance("", "scene_break", paragraph=idx))
            inner = False
            continue
        if '"' in p.text:
            utts = _parse_quoted(p.text, idx, rules)
            _link_speakers(utts, out[-1] if out else None)
            inner = False
        elif inner:
            utts, inner = _parse_inner(p.text, idx)
        else:
            utts = [Utterance(p.text, paragraph=idx)]
        for u in utts:
            u.paragraph_kind = p.kind
        out.extend(utts)
        last = utts[-1] if utts else None
        if last is not None and last.role == "narration" and last.text.endswith(":") \
                and any(t in last.text.casefold() for t in _INNER_TRIGGERS):
            last.pause_after = rules["inner_voice"]
            inner = True
    return out
