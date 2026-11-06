import json
import pytest
import httpx
from src.core.version_config import (
    APP_VERSION,
    DEFAULT_UPDATE_URL,
    parse_version,
    is_newer_version,
)
from src.config import settings
from src.core.update_manager import UpdateManager, UpdateInfo


def test_version_config_constants():
    assert isinstance(APP_VERSION, str)
    assert len(APP_VERSION.split(".")) >= 2
    assert isinstance(DEFAULT_UPDATE_URL, str)
    assert DEFAULT_UPDATE_URL.startswith("http")


def test_parse_version():
    assert parse_version("1.0.0") == (1, 0, 0)
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("2.10.4-beta") == (2, 10, 4)
    assert parse_version("invalid") == (0, 0, 0)


def test_is_newer_version():
    assert is_newer_version("1.0.1", "1.0.0") is True
    assert is_newer_version("1.1.0", "1.0.9") is True
    assert is_newer_version("2.0.0", "1.99.99") is True
    assert is_newer_version("1.0.0", "1.0.0") is False
    assert is_newer_version("0.9.9", "1.0.0") is False
    assert is_newer_version("v1.0.5", "1.0.4") is True


def test_settings_update_url_default():
    assert hasattr(settings, "update_url")
    assert settings.update_url.startswith("http")


@pytest.mark.asyncio
async def test_update_manager_check_newer_version(monkeypatch, tmp_path):
    mock_payload = {
        "version": "1.0.5",
        "release_date": "2026-10-20",
        "changelog": "Tính năng mới & sửa lỗi",
        "platforms": {
            "windows": {
                "url": "https://example.com/TedCompanion-1.0.5.exe",
                "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "size": 100
            },
            "macos": {
                "url": "https://example.com/TedCompanion-1.0.5.zip",
                "sha256": "abcdef",
                "size": 200
            }
        }
    }

    async def mock_get(self, url, *args, **kwargs):
        class MockResponse:
            status_code = 200
            def json(self):
                return mock_payload
            def raise_for_status(self):
                pass
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    mgr = UpdateManager(updates_dir=tmp_path)
    info = await mgr.check_for_updates("https://example.com/version.json", current_version="1.0.0")
    assert info is not None
    assert info.version == "1.0.5"
    assert info.changelog == "Tính năng mới & sửa lỗi"
    assert info.url.startswith("https://example.com/")


@pytest.mark.asyncio
async def test_update_manager_check_same_or_older_version(monkeypatch, tmp_path):
    mock_payload = {
        "version": "1.0.0",
        "platforms": {"windows": {"url": "https://example.com/test.exe"}}
    }

    async def mock_get(self, url, *args, **kwargs):
        class MockResponse:
            status_code = 200
            def json(self):
                return mock_payload
            def raise_for_status(self):
                pass
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    mgr = UpdateManager(updates_dir=tmp_path)
    info = await mgr.check_for_updates("https://example.com/version.json", current_version="1.0.0")
    assert info is None


@pytest.mark.asyncio
async def test_update_manager_download_and_verify(monkeypatch, tmp_path):
    import hashlib
    content = b"Binary executable content for Ted Companion test"
    expected_sha256 = hashlib.sha256(content).hexdigest()

    class MockStreamContext:
        async def __aenter__(self):
            class MockStreamResponse:
                status_code = 200
                headers = {}
                def raise_for_status(self):
                    pass
                async def aiter_bytes(self, chunk_size=8192):
                    yield content
            return MockStreamResponse()

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_stream(self, method, url, *args, **kwargs):
        return MockStreamContext()

    monkeypatch.setattr(httpx.AsyncClient, "stream", mock_stream)

    mgr = UpdateManager(updates_dir=tmp_path)
    info = UpdateInfo(
        version="1.0.5",
        release_date="2026-10-20",
        changelog="New version",
        url="https://example.com/TedCompanion-1.0.5.exe",
        sha256=expected_sha256,
        size=len(content),
        platform_key="windows",
        file_name="pending_update.exe"
    )

    downloaded_path = await mgr.download_update(info)
    assert downloaded_path.exists()
    assert downloaded_path.read_bytes() == content

    ready = mgr.get_pending_update()
    assert ready is not None
    assert ready["version"] == "1.0.5"

    mgr.clear_pending_update()
    assert mgr.get_pending_update() is None

