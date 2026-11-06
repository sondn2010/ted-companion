"""Compatibility wrapper for legacy hermes_connections_manage_dialog imports."""
from src.ui.dashboard_tabs.openai_connections_manage_dialog import (
    OpenAIConnectionsManageDialog as HermesConnectionsManageDialog,
)

__all__ = ["HermesConnectionsManageDialog"]
