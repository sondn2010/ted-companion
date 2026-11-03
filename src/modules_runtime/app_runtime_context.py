"""Bối cảnh runtime dùng chung cho mọi engine (dependency được inject từ main.py)."""

from dataclasses import dataclass
from typing import Any


@dataclass
class AppRuntimeContext:
    # Kiểu Any có chủ đích: tránh import vòng giữa UI/engine; các phase sau thu hẹp kiểu khi cần.
    focus_engine: Any = None
    audio: Any = None
    registry: Any = None
    client_pool: Any = None
    bubble: Any = None
    quick_chat: Any = None
    dashboard: Any = None
    kv: Any = None
    engine_host: Any = None
    gamification: Any = None   # GamificationHubService (Hub XP/level/badge), tạo trong main.py
