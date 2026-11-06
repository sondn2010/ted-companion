import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.core.update_manager import UpdateInfo, UpdateManager
from src.core.version_config import APP_VERSION
from src.core.i18n import tr


@pytest.mark.asyncio
async def test_startup_update_prompt_and_accept(monkeypatch, tmp_path):
    mgr = UpdateManager(updates_dir=tmp_path)

    fake_info = UpdateInfo(
        version="1.0.5",
        release_date="2026-10-20",
        changelog="New release",
        url="https://example.com/download.exe",
        platform_key="windows",
        file_name="pending_update.exe",
    )

    # Mock check_for_updates to return fake_info
    monkeypatch.setattr(mgr, "check_for_updates", AsyncMock(return_value=fake_info))

    # Mock download_update
    download_mock = AsyncMock(return_value=tmp_path / "pending_update.exe")
    monkeypatch.setattr(mgr, "download_update", download_mock)

    class MockBubble:
        def __init__(self):
            self.last_text = ""
            self.last_actions = []
            self.hidden = False

        def show_message(self, text, mood=None, actions=(), timeout_ms=0):
            self.last_text = text
            self.last_actions = list(actions)

        def hide(self):
            self.hidden = True

    bubble = MockBubble()

    # Chạy quy trình prompt
    await mgr.run_startup_update_flow(bubble, update_url="https://example.com/version.json")

    # Kiểm tra bubble đã hiển thị câu hỏi và 2 nút
    assert "1.0.5" in bubble.last_text
    assert len(bubble.last_actions) == 2

    # Giả lập người dùng bấm nút [Cập nhật ngay] (action thứ 1)
    accept_caption, accept_callback = bubble.last_actions[0]
    assert accept_caption == tr("update_btn_accept")

    accept_callback()
    # Chờ coroutine tải chạy xong
    await asyncio.sleep(0.05)

    assert download_mock.called
