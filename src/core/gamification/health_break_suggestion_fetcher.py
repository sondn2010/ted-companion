"""Hỏi Não AI (OpenAI-compatible) một gợi ý sức khỏe nhỏ; quá hạn/lỗi → None để dùng bảng offline."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from src.bridge.openai_json_contract_request import request_openai_json_contract
from src.core.gamification.health_break_contract_schema import HealthBreakSuggestion

request_json = request_openai_json_contract
request_hermes_json_contract = request_openai_json_contract

logger = logging.getLogger("ted")

AI_TIMEOUT_SECS = 3.0   # quá 3 giây là bỏ, dùng bảng offline (không để user chờ sau phiên focus)
HERMES_TIMEOUT_SECS = AI_TIMEOUT_SECS


@dataclass(frozen=True)
class HealthBreakContext:
    session_minutes: int
    breaks_today: int
    micro_done_today: int
    minutes_since_water: Optional[float]
    minutes_since_move: Optional[float]
    local_hour: int
    health_stat: Optional[int]
    recent_kinds: Sequence[str] = ()
    language: str = "vi"


def _fmt(value) -> str:
    return "unknown" if value is None else str(int(value))


def build_health_break_prompt(ctx: HealthBreakContext) -> str:
    """Chỉ số nguyên đã tổng hợp, không có tên việc/nội dung riêng tư."""
    return (
        f"[TED_HEALTH_BREAK] session_minutes={ctx.session_minutes} breaks_today={ctx.breaks_today} "
        f"micro_done_today={ctx.micro_done_today} since_water_min={_fmt(ctx.minutes_since_water)} "
        f"since_move_min={_fmt(ctx.minutes_since_move)} local_hour={ctx.local_hour} "
        f"health={_fmt(ctx.health_stat)} recent_kinds={','.join(ctx.recent_kinds) or 'none'} lang={ctx.language}\n"
        "Chỉ trả về JSON hợp lệ trong <json></json>."
    )


async def fetch_health_break_suggestion(client, ctx: HealthBreakContext,
                                       timeout: float = AI_TIMEOUT_SECS) -> Optional[HealthBreakSuggestion]:
    """Không bao giờ raise: mọi lỗi/timeout → None."""
    try:
        return await asyncio.wait_for(
            request_openai_json_contract(client, build_health_break_prompt(ctx), HealthBreakSuggestion, timeout=timeout), timeout)
    except asyncio.TimeoutError:
        logger.info("Health-break AI quá %.0fs, dùng gợi ý offline", timeout)
    except Exception:  # noqa: BLE001 - gợi ý sức khỏe là phụ, không được làm hỏng app
        logger.warning("Health-break AI lỗi, dùng gợi ý offline", exc_info=True)
    return None


# Backward compatibility alias
fetch_hermes_suggestion = fetch_health_break_suggestion
