"""Compatibility wrapper for legacy hermes_connection_edit_dialog imports."""
from src.ui.dashboard_tabs.openai_connection_edit_dialog import (
    OpenAIConnectionEditDialog as HermesConnectionEditDialog,
)

__all__ = ["HermesConnectionEditDialog"]
