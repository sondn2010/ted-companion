"""Compatibility wrapper for legacy hermes_client imports."""
from src.bridge.openai_client import (
    OpenAIBrainClient as HermesBrainClient,
    OpenAIBrainClient as HermesClient,
    OpenAIUnavailableError as HermesUnavailableError,
    OpenAIRequestRejectedError as HermesRequestRejectedError,
    SYSTEM_FALLBACK_PROMPT,
    sanitize_for_history,
)

__all__ = [
    "HermesBrainClient",
    "HermesClient",
    "HermesUnavailableError",
    "HermesRequestRejectedError",
    "SYSTEM_FALLBACK_PROMPT",
    "sanitize_for_history",
]
