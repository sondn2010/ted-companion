"""VieNeu phase 03: UI cài đặt (chọn giọng, nhãn tiến trình, ghi chú tải), preset Docker, chống đường dẫn dài,
watchdog sidecar mồ côi, RemoteOpenAITTSEngine thử lại WAV."""

import asyncio
import importlib.util
import json
import os
import subprocess
import sys

import httpx
import pytest
from PySide6.QtWidgets import QLabel, QWidget

from qt_offscreen_app_helper import flush_qt_garbage, get_qapp

from src.config import settings
from src.core import offline_voice_model_store as store
from src.core import vieneu_runtime_installer as installer
from src.core import vieneu_runtime_paths as paths
from src.core.offline_voice_model_catalog import VIENEU_MARKER_FILE, get_model
from src.core.tts_service import RemoteOpenAITTSEngine, fix_streaming_wav_header
from src.core.vieneu_sidecar_tts_engine import VieneuVoice
from src.core.voice_config_presets import get_preset, search_presets
from src.ui.dashboard_tabs import vieneu_voice_picker_widget as picker_mod
from src.ui.dashboard_tabs.offline_voice_model_download_dialog import (
    VIENEU_DOWNLOAD_NOTE, OfflineVoiceModelDownloadDialog,
)
from src.ui.dashboard_tabs.vieneu_voice_picker_widget import VieneuVoicePickerWidget
from src.ui.dashboard_tabs.voice_download_progress_text import format_download_progress

spec = importlib.util.spec_from_file_location("vieneu_sidecar_hardening", paths.sidecar_script_path())
sidecar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sidecar)

VOICES = [VieneuVoice("Hải Đăng", "Hải Đăng", True), VieneuVoice("Mai Anh", "Mai Anh")]


@pytest.fixture(autouse=True)
def _flush_widgets_after_test():
    yield
    flush_qt_garbage()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(store.shutil, "which", lambda _n: None)
    monkeypatch.setattr(settings, "vieneu_voices", {})
    monkeypatch.setattr(settings, "tts_local_voice_vi", "")
    monkeypatch.setattr(picker_mod, "spawn_background_task", lambda coro, name: coro.close())   # không có event loop thật
    return tmp_path


def _mark_installed(model_id: str) -> None:
    model_dir = store.model_dir(get_model(model_id))
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / VIENEU_MARKER_FILE).write_text("{}", encoding="utf-8")


# ---------------- nhãn tiến trình ----------------
def test_progress_text_stage_labels_are_natural_and_busy():
    view = format_download_progress(0, 0, "[3/4] Cài thư viện VieNeu (khoảng 500 MB, có thể vài phút)")
    assert view.text.startswith("Bước 3/4: Cài thư viện") and "10–15 phút" in view.text and not view.determinate
    assert format_download_progress(0, 0, "[1/4] Tải công cụ uv").text == "Bước 1/4: Tải công cụ cài đặt…"
    assert format_download_progress(0, 0, "[9/9] Việc lạ").text == "Bước 9/9: Việc lạ…"   # bước không có trong bảng


def test_progress_text_real_bytes_and_plain_label():
    view = format_download_progress(5 * 1048576, 10 * 1048576, "bộ chạy offline")
    assert view.determinate and view.permille == 500 and "5/10 MB" in view.text
    plain = format_download_progress(3 * 1048576, 0, "Piper")
    assert not plain.determinate and plain.text == "Đang tải Piper… 3 MB"


def test_dialog_shows_vieneu_note_busy_bar_and_does_not_preselect_it(home):
    get_qapp()
    dialog = OfflineVoiceModelDownloadDialog("tts")
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert VIENEU_DOWNLOAD_NOTE in texts and "15–20 phút" in texts and "Khuyên dùng" in texts
    turbo = next(r for r in dialog.rows if r.model.id == "vieneu-v3-turbo")
    assert not turbo.check.isChecked()   # tải ~1,4 GB: không tích sẵn
    dialog._on_progress(0, 0, "[3/4] x")
    assert dialog.progress.maximum() == 0 and dialog.lbl_status.text().startswith("Bước 3/4")
    dialog._on_progress(1048576, 2097152, "bộ chạy offline")
    assert dialog.progress.maximum() == 1000 and dialog.progress.value() == 500


# ---------------- chọn giọng ----------------
def test_picker_hidden_for_piper_or_not_installed(home):
    get_qapp()
    parent = QWidget()
    widget = VieneuVoicePickerWidget(provider=None, parent=parent)
    widget.set_model("vieneu-v3-turbo")   # chưa cài
    assert widget._model_id == ""
    widget.set_model("piper-vi-vais1000-medium")
    assert widget._model_id == ""


def test_picker_loads_async_restores_saved_and_persists(home, monkeypatch):
    get_qapp()
    _mark_installed("vieneu-v3-turbo")
    monkeypatch.setattr(settings, "vieneu_voices", {"vieneu-v3-turbo": "Mai Anh"})
    calls = []

    async def provider(model_id):
        calls.append(model_id)
        return VOICES

    parent = QWidget()   # giữ tham chiếu: parent bị GC thì widget con bị xoá theo
    widget = VieneuVoicePickerWidget(provider=provider, parent=parent)
    widget.set_model("vieneu-v3-turbo")
    asyncio.run(widget.load())
    assert calls == ["vieneu-v3-turbo"]
    assert [widget.combo.itemData(i) for i in range(widget.combo.count())] == ["", "Hải Đăng", "Mai Anh"]
    assert widget.combo.itemText(0) == "Mặc định (Hải Đăng)"
    assert widget.combo.currentData() == "Mai Anh" and widget.combo.isEnabled()
    widget.combo.setCurrentIndex(1)
    widget.commit()
    assert settings.vieneu_voices["vieneu-v3-turbo"] == "Hải Đăng"
    widget.combo.setCurrentIndex(0)
    widget.commit()
    assert settings.vieneu_voices["vieneu-v3-turbo"] == ""


def test_picker_error_state_then_retry_succeeds_and_failed_load_keeps_saved_voice(home, monkeypatch):
    get_qapp()
    _mark_installed("vieneu-v3-nano")
    monkeypatch.setattr(settings, "vieneu_voices", {"vieneu-v3-nano": "Mai Anh"})
    attempts = []

    async def flaky(model_id):
        attempts.append(model_id)
        if len(attempts) == 1:
            raise RuntimeError("Sidecar VieNeu thoát sớm.\nchi tiết log")
        return VOICES

    parent = QWidget()
    widget = VieneuVoicePickerWidget(provider=flaky, parent=parent)
    widget.set_model("vieneu-v3-nano")
    asyncio.run(widget.load())
    assert not widget.btn_retry.isHidden() and not widget.combo.isEnabled() and "thoát sớm" in widget.lbl_state.text()
    widget.commit()
    assert settings.vieneu_voices["vieneu-v3-nano"] == "Mai Anh"   # lỗi nạp → không ghi đè lựa chọn đã lưu
    asyncio.run(widget.load())   # = bấm Thử lại
    assert widget.btn_retry.isHidden() and widget.combo.currentData() == "Mai Anh" and len(attempts) == 2


def test_picker_test_button_commits_then_requests_test(home):
    get_qapp()
    _mark_installed("vieneu-v3-turbo")

    async def provider(_model_id):
        return VOICES

    parent = QWidget()   # giữ tham chiếu: parent bị GC thì widget con bị xoá theo
    widget = VieneuVoicePickerWidget(provider=provider, parent=parent)
    widget.set_model("vieneu-v3-turbo")
    asyncio.run(widget.load())
    widget.combo.setCurrentIndex(2)
    seen = []
    widget.test_requested.connect(lambda: seen.append(settings.vieneu_voices["vieneu-v3-turbo"]))
    widget.btn_test.click()
    assert seen == ["Mai Anh"]


def test_tts_group_wires_picker_to_selected_local_vi_model(home, monkeypatch):
    get_qapp()
    from src.ui.dashboard_tabs.tts_settings_group_widget import TtsSettingsGroupWidget
    _mark_installed("vieneu-v3-turbo")
    monkeypatch.setattr(settings, "tts_local_voice_vi", "vieneu-v3-turbo")
    group = TtsSettingsGroupWidget()
    assert group.voice_picker._model_id == "vieneu-v3-turbo"


# ---------------- preset Docker ----------------
def test_docker_preset_present_searchable_and_valid():
    preset = get_preset("tts-vieneu-docker")
    assert preset and preset.values["tts_mode"] == "server"
    assert preset.values["tts_server_url"] == "http://localhost:8000/v1" and preset.values["tts_voice_vi"] == "Hải Đăng"
    for query in ("vieneu", "tiếng việt docker", "tieng viet", "docker cpu"):
        assert preset in search_presets("tts", query)


# ---------------- đường dẫn dài ----------------
def test_long_env_path_rejected_on_windows_only(tmp_path):
    long_dir = tmp_path / ("x" * 120)   # > 80 ký tự
    with pytest.raises(RuntimeError, match="TED_HOME"):
        paths.check_env_path_length(long_dir, windows=True)
    paths.check_env_path_length(long_dir, windows=False)
    paths.check_env_path_length(tmp_path.anchor and type(tmp_path)(tmp_path.anchor) / "short", windows=True)


def test_install_fails_fast_on_long_path_before_any_download(home, monkeypatch):
    monkeypatch.setattr(paths, "MAX_WINDOWS_ENV_PATH_CHARS", 5)
    monkeypatch.setattr(installer, "check_env_path_length", lambda: paths.check_env_path_length(windows=True))
    called = []

    async def boom(*_args, **_kwargs):
        called.append(1)

    monkeypatch.setattr(installer, "ensure_runtime", boom)
    with pytest.raises(RuntimeError, match="quá dài"):
        asyncio.run(installer.install_vieneu(get_model("vieneu-v3-nano")))
    assert not called


# ---------------- sidecar mồ côi ----------------
def test_is_process_alive_for_self_dead_child_and_invalid():
    assert sidecar.is_process_alive(os.getpid())
    assert not sidecar.is_process_alive(0) and not sidecar.is_process_alive(-5)
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert not sidecar.is_process_alive(child.pid)


def test_parent_watchdog_fires_when_parent_gone():
    states = iter([True, True, False])
    fired = []
    thread = sidecar.start_parent_watchdog(1, interval_s=0.01, on_gone=lambda: fired.append(1),
                                           alive=lambda _pid: next(states))
    thread.join(timeout=3)
    assert fired == [1] and thread.daemon


# ---------------- máy chủ chỉ hỗ trợ WAV (VieNeu Docker) ----------------
def test_remote_engine_retries_with_wav_when_mp3_rejected():
    formats = []
    wav = (b"RIFF" + b"\xff\xff\xff\xff" + b"WAVEfmt " + b"\x00" * 20 + b"data" + b"\xff\xff\xff\xff"
           + b"\x01\x02" * 10)

    def handler(request):
        fmt = json.loads(request.content)["response_format"]
        formats.append(fmt)
        if fmt == "mp3":
            return httpx.Response(400, text="response_format 'mp3' not supported; use 'pcm' or 'wav'")
        return httpx.Response(200, content=wav)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            engine = RemoteOpenAITTSEngine("http://x/v1", "", "m")
            return await engine.synthesize("xin chào", "Hải Đăng", 1.0, http_client=client)

    out = asyncio.run(run())
    assert formats == ["mp3", "wav"] and out == fix_streaming_wav_header(wav)
    assert int.from_bytes(out[4:8], "little") == len(out) - 8 and int.from_bytes(out[40:44], "little") == len(out) - 44


def test_fix_wav_header_ignores_non_wav():
    assert fix_streaming_wav_header(b"ID3abc") == b"ID3abc"
