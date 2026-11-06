import json
from pathlib import Path
import pytest

from scripts.publish_release import create_release_manifest


def test_create_release_manifest(tmp_path):
    dummy_exe = tmp_path / "TedCompanion.exe"
    dummy_exe.write_bytes(b"Test release binary content")

    manifest = create_release_manifest(
        version="1.0.1",
        binary_path=dummy_exe,
        url_base="https://updates.example.com/ted/releases",
        changelog="Sửa lỗi giao diện và thêm auto update",
        platform_key="windows",
    )

    assert manifest["version"] == "1.0.1"
    assert "windows" in manifest["platforms"]
    plat = manifest["platforms"]["windows"]
    assert plat["url"] == "https://updates.example.com/ted/releases/TedCompanion-1.0.1-windows.exe"
    assert len(plat["sha256"]) == 64
    assert plat["size"] == len(b"Test release binary content")
