"""Dựng tin chat gỡ rối + yêu cầu phản biện JSON gửi Hermes của module đang active (client None → None)."""

import logging
import re
from typing import Mapping, Optional, Sequence

from src.bridge.hermes_json_contract_request import request_json
from src.core.idea_untangle.untangle_critique_contract_schemas import UntangleCritique
from src.core.idea_untangle.untangle_problem_kinds_by_engine import audience_for, normalize_kind
from src.core.idea_untangle.untangle_prompt_templates import AUDIENCE_RULES, CHAT_PREFIX, CRITIQUE_TEMPLATE
from src.modules_runtime.prompt_template_renderer import render_prompt

logger = logging.getLogger("ted")

MAX_TURNS = 20
MAX_TRANSCRIPT_CHARS = 6000
CRITIQUE_TIMEOUT_SECS = 90.0
_TAG_BREAKERS_RE = re.compile(r"</?\s*(?:transcript|json)\s*>", re.I)


def _clean(text: str) -> str:
    """Bỏ thẻ </transcript>/<json> do người dùng gõ (không cho phá cấu trúc prompt)."""
    return _TAG_BREAKERS_RE.sub("", text)


def build_chat_message(engine: str, kind: str, task_title: str, message: str) -> str:
    """Tin chat có thẻ giao thức; task_title bị làm phẳng 1 dòng, bỏ dấu nháy kép."""
    task = " ".join(_clean(task_title).replace('"', "'").split())[:120]
    return render_prompt(CHAT_PREFIX, {"kind": normalize_kind(engine, kind), "audience": audience_for(engine),
                                       "task": task, "message": message})


def render_transcript(turns: Sequence[Mapping[str, str]]) -> str:
    """≤20 lượt mới nhất, ≤6000 ký tự (cắt từ lượt cũ nhất); mỗi dòng 'Người dùng:'/'Ted:'."""
    lines = []
    for turn in list(turns)[-MAX_TURNS:]:
        who = "Người dùng" if turn.get("role") == "user" else "Ted"
        text = _clean(str(turn.get("text", ""))).strip()
        if text:
            lines.append(f"{who}: {text}")
    while len(lines) > 1 and sum(len(ln) + 1 for ln in lines) > MAX_TRANSCRIPT_CHARS:
        lines.pop(0)
    return "\n".join(lines)[-MAX_TRANSCRIPT_CHARS:]


def build_critique_prompt(engine: str, kind: str, turns: Sequence[Mapping[str, str]]) -> str:
    audience = audience_for(engine)
    return render_prompt(CRITIQUE_TEMPLATE, {
        "audience": audience, "kind": normalize_kind(engine, kind),
        "transcript": render_transcript(turns), "audience_rules": AUDIENCE_RULES.get(audience, ""),
    })


async def request_untangle_critique(client, engine: str, kind: str,
                                    turns: Sequence[Mapping[str, str]]) -> Optional[UntangleCritique]:
    """None khi không có client / offline / JSON hỏng (bên gọi hiện lỗi, giữ nguyên cuộc chat)."""
    if client is None or not render_transcript(turns):
        return None
    try:
        return await request_json(client, build_critique_prompt(engine, kind, turns), UntangleCritique,
                                  timeout=CRITIQUE_TIMEOUT_SECS)
    except Exception:  # lỗi bất ngờ không được làm sập dialog
        logger.exception("Phản biện Gỡ Rối thất bại")
        return None
