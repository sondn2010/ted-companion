"""Xin Hermes tóm tắt email (skill ted-email-digest) → EmailDigestResponse; tắt/không client/lỗi → None."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from src.bridge.openai_json_contract_request import request_openai_json_contract as request_json
from src.engines.work.email_digest_contract_schemas import EmailDigestResponse
from src.engines.work.local_timezone_name import local_timezone_name
from src.engines.work.work_briefing_due_window import MIDDAY
from src.modules_runtime.prompt_template_renderer import load_prompt

logger = logging.getLogger("ted")
EMAIL_DIGEST_TIMEOUT_SECS = 45.0  # mỗi lần gọi HTTP (request_json có thể thử lại 1 lần)
EMAIL_DIGEST_BUDGET_SECS = 22.0   # trần tổng cho cả 2 lần thử: không để briefing chờ 2x45s


async def fetch_email_digest(
    manifest, client, slot: str, since: Optional[datetime] = None
) -> Optional[EmailDigestResponse]:
    """since: mốc bắt đầu quét email (trưa = từ briefing sáng); None → cửa sổ giờ theo settings."""
    settings = manifest.settings
    if not settings.get("email_digest_enabled", True) or client is None:
        return None
    key, default = ("midday_email_lookback_hours", 6) if slot == MIDDAY else ("email_lookback_hours", 16)
    since = since or datetime.now().astimezone() - timedelta(hours=max(1, int(settings.get(key, default))))
    prompt = load_prompt(manifest, "email_digest_request", {
        "since": since.isoformat(timespec="minutes"),
        "tz": local_timezone_name(settings.get("timezone")),
        "max": int(settings.get("email_max_items", 8)),
    })
    if not prompt:
        return None
    try:
        return await asyncio.wait_for(
            request_json(client, prompt, EmailDigestResponse, timeout=EMAIL_DIGEST_TIMEOUT_SECS),
            EMAIL_DIGEST_BUDGET_SECS,
        )
    except asyncio.TimeoutError:
        logger.info("Lấy email digest quá %.0fs, bỏ qua", EMAIL_DIGEST_BUDGET_SECS)
        return None
    except Exception:  # lỗi lạ không được làm hỏng briefing
        logger.exception("Lấy email digest lỗi")
        return None
