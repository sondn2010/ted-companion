"""Loại vấn đề Gỡ Rối theo engine (work/coach) + audience. Engine lạ → dùng bộ của work."""

from typing import Tuple

WORK_KINDS: Tuple[str, ...] = ("algorithm", "thinking_block", "architecture", "other")
COACH_KINDS: Tuple[str, ...] = ("math_problem", "concept", "essay_structure", "other")
KINDS_BY_ENGINE = {"work": WORK_KINDS, "coach": COACH_KINDS}
DEFAULT_KIND = "other"
AUDIENCE_WORK = "work"
AUDIENCE_LEARNER = "learner"


def kinds_for(engine: str) -> Tuple[str, ...]:
    return KINDS_BY_ENGINE.get(engine, WORK_KINDS)


def normalize_kind(engine: str, kind: str) -> str:
    """Kind không thuộc bộ của engine → 'other' (tránh chèn tuỳ ý vào thẻ giao thức)."""
    return kind if kind in kinds_for(engine) else DEFAULT_KIND


def audience_for(engine: str) -> str:
    """coach → người học (Socratic, kid-safe); còn lại → người đi làm."""
    return AUDIENCE_LEARNER if engine == "coach" else AUDIENCE_WORK


def kind_i18n_key(kind: str) -> str:
    """Khoá i18n nhãn loại vấn đề (phase 06 khai báo vi/en)."""
    return f"untangle.kind.{kind}"
