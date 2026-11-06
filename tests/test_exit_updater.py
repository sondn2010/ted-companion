import os
from pathlib import Path
import sys
import pytest

from src.core.exit_updater import (
    generate_windows_updater_script,
    generate_macos_updater_script,
    apply_update_on_exit,
)


def test_generate_windows_updater_script(tmp_path):
    script_path = tmp_path / "update_helper.bat"
    content = generate_windows_updater_script(script_path)
    assert script_path.exists()
    assert "@echo off" in content
    assert "tasklist" in content
    assert "copy /y" in content


def test_generate_macos_updater_script(tmp_path):
    script_path = tmp_path / "update_helper.sh"
    content = generate_macos_updater_script(script_path)
    assert script_path.exists()
    assert "#!/bin/bash" in content
    assert "kill -0" in content


def test_apply_update_on_exit_in_dev_mode(monkeypatch, tmp_path):
    # In dev mode, sys.frozen is False -> should not launch detached updater
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    dummy_exe = tmp_path / "TedCompanion.exe"
    dummy_update = tmp_path / "pending_update.exe"
    dummy_update.write_bytes(b"dummy")

    result = apply_update_on_exit(
        executable_path=dummy_exe,
        pending_file=dummy_update,
        updates_dir=tmp_path,
        pid=1234,
        relaunch=True,
    )
    assert result is False


def test_apply_update_on_exit_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    dummy_exe = tmp_path / "TedCompanion.exe"
    missing_update = tmp_path / "non_existent.exe"

    result = apply_update_on_exit(
        executable_path=dummy_exe,
        pending_file=missing_update,
        updates_dir=tmp_path,
        pid=1234,
        relaunch=True,
    )
    assert result is False
