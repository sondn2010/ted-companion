"""Compatibility wrapper for legacy hermes_connections_settings_widget imports."""
from src.ui.dashboard_tabs.openai_connections_settings_widget import (
    OpenAIConnectionsSettingsWidget as HermesConnectionsSettingsWidget,
    COL_NAME,
    COL_URL,
    COL_MODEL,
    COL_STATUS,
)

__all__ = [
    "HermesConnectionsSettingsWidget",
    "COL_NAME",
    "COL_URL",
    "COL_MODEL",
    "COL_STATUS",
]
