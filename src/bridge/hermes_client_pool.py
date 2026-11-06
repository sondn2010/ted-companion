"""Compatibility wrapper for legacy hermes_client_pool imports."""
from src.bridge.openai_client_pool import (
    OpenAIClientPool as HermesClientPool,
    openai_client_pool as hermes_client_pool,
    ManifestConnectionResolver,
)

__all__ = ["HermesClientPool", "hermes_client_pool", "ManifestConnectionResolver"]
