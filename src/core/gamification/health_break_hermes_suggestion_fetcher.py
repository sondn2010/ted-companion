"""Compatibility wrapper for legacy health_break_hermes_suggestion_fetcher imports."""
from src.core.gamification.health_break_suggestion_fetcher import (
    AI_TIMEOUT_SECS,
    HERMES_TIMEOUT_SECS,
    HealthBreakContext,
    build_health_break_prompt,
    fetch_health_break_suggestion as fetch_hermes_suggestion,
    fetch_health_break_suggestion,
    request_json,
    request_openai_json_contract,
    request_hermes_json_contract,
)

__all__ = [
    "AI_TIMEOUT_SECS",
    "HERMES_TIMEOUT_SECS",
    "HealthBreakContext",
    "build_health_break_prompt",
    "fetch_hermes_suggestion",
    "fetch_health_break_suggestion",
    "request_json",
    "request_openai_json_contract",
    "request_hermes_json_contract",
]
