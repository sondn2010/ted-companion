"""Giọng nói offline tải trong app + preset cấu hình:
1. Catalog / preset hợp lệ (≥ 20 preset, model tham chiếu tồn tại, khoá settings có thật, tìm kiếm không dấu).
2. Tải model + bộ chạy qua HTTP (MockTransport): tiến trình, không để lại .part, huỷ giữa chừng, chặn path traversal.
3. Engine offline gọi đúng binary piper / whisper-cli; settings lưu bền các trường STT + model offline.
4. UI: preset điền vào ô nhập, tải xong tự chuyển offline + chọn model, popup tìm kiếm & popup tải.
"""

import asyncio
import dataclasses
import hashlib
import io
from pathlib import Path
import subprocess
import zipfile

import httpx
import pytest
from PySide6.QtWidgets import QMessageBox

from qt_offscreen_app_helper import flush_qt_garbage, get_qapp

from src.config import AppConfig, settings
from src.core import offline_voice_model_store as store
from src.core.offline_voice_model_catalog import OFFLINE_VOICE_MODELS, get_model, models_for, runtime_for
from src.core.stt_service import LocalEmbeddedSTTEngine
from src.core.tts_service import LocalEmbeddedTTSEngine, is_embedded_tts_available
from src.core.voice_config_presets import VOICE_CONFIG_PRESETS, fold_accents, presets_for, search_presets



@pytest.fixture(autouse=True)
def _flush_widgets_after_test():
    yield
    flush_qt_garbage()

@pytest.fixture
def voice_home(tmp_path, monkeypatch):
    """settings.data_dir trỏ vào thư mục tạm: mọi model 'tải' trong test nằm ở đây."""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(store.shutil, "which", lambda _name: None)   # không dò nhầm binary thật trong PATH
    for key in [k for k in vars(settings) if k.startswith(("tts_", "stt_"))]:
        monkeypatch.setattr(settings, key, getattr(settings, key))   # widget ghi vào settings → khôi phục sau test
    return tmp_path


def _fake_install(model, runtime_exe_name: str = None):
    for _url, name in model.files:
        target = store.model_dir(model) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"model")
    exe = store.runtime_dir(model.kind) / "bin" / (runtime_exe_name or runtime_for(model.kind).executable)
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"exe")
    return exe


# ---------------- 1. catalog & presets ----------------
def test_catalog_has_recommended_models_per_language_and_https_urls():
    assert {m.id for m in OFFLINE_VOICE_MODELS} == {m.id for m in models_for("tts")} | {m.id for m in models_for("stt")}
    for kind, lang in (("tts", "vi"), ("tts", "en"), ("stt", None)):
        assert any(m.recommended for m in models_for(kind, lang))
    assert all(url.startswith("https://") for m in OFFLINE_VOICE_MODELS for url, _ in m.files)
    assert runtime_for("tts", "win").executable == "piper.exe"
    assert runtime_for("stt", "win").url and runtime_for("stt", "mac-arm").url is None
    assert "brew install whisper-cpp" in runtime_for("stt", "mac-arm").manual_hint


def test_presets_are_about_twenty_valid_and_reference_real_models_and_settings():
    assert len(VOICE_CONFIG_PRESETS) >= 20
    assert len({p.id for p in VOICE_CONFIG_PRESETS}) == len(VOICE_CONFIG_PRESETS)
    for preset in VOICE_CONFIG_PRESETS:
        assert all(get_model(mid) is not None for mid in preset.requires_models), preset.id
        assert all(hasattr(settings, key) and key.startswith(preset.kind) for key in preset.values), preset.id
    assert len(presets_for("tts")) >= 10 and len(presets_for("stt")) >= 8


def test_preset_search_is_accent_insensitive_and_multi_word():
    assert fold_accents("Đọc chậm cho Học Sinh") == "doc cham cho hoc sinh"
    ids = [p.id for p in search_presets("tts", "cham hoc sinh")]
    assert "tts-offline-student-slow" in ids and "tts-edge-student" in ids
    assert [p.id for p in search_presets("stt", "groq")] == ["stt-groq-turbo"]
    assert search_presets("tts", "khong-ton-tai-xyz") == []


# ---------------- 2. download ----------------
def _zip_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _mock_client(routes: dict, gate: asyncio.Event = None) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = routes.get(str(request.url))
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, content=body, headers={"content-length": str(len(body))})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_download_model_fetches_runtime_and_files_with_progress(voice_home, monkeypatch):
    archive = _zip_bytes({"piper/piper.exe": b"exe", "piper/espeak-ng-data/x": b"d"})
    win = dataclasses.replace(runtime_for("tts", "win"), sha256=hashlib.sha256(archive).hexdigest())
    monkeypatch.setattr(store, "runtime_for", lambda kind, *_: win)
    model = get_model("piper-vi-vivos-xlow")
    routes = {win.url: archive}
    routes.update({url: b"M" * 1000 for url, _ in model.files})
    progress = []
    async with _mock_client(routes) as client:
        path = await store.download_model(model, lambda d, t, label: progress.append((d, label)), client=client)
    assert path == store.model_main_path(model) and path.read_bytes() == b"M" * 1000
    assert store.is_model_installed(model)
    assert store.find_runtime_executable("tts", win).name == "piper.exe"
    assert not list(voice_home.rglob("*.part")) and not list((voice_home / "voice_models" / "runtime").glob("*.zip"))
    assert any(label == model.title for _d, label in progress)


async def test_download_cancel_leaves_no_partial_files(voice_home, monkeypatch):
    model = get_model("whisper-tiny-q5")
    _fake_install(model)   # bộ chạy đã có
    store.delete_model(model)
    cancel = asyncio.Event()
    cancel.set()
    async with _mock_client({url: b"x" * 5000 for url, _ in model.files}) as client:
        with pytest.raises(store.DownloadCancelled):
            await store.download_model(model, cancel=cancel, client=client)
    assert not store.is_model_installed(model)
    assert not list(voice_home.rglob("*.part"))


async def test_download_http_error_is_reported_in_vietnamese(voice_home):
    model = get_model("whisper-tiny-q5")
    _fake_install(model)
    store.delete_model(model)
    async with _mock_client({}) as client:
        with pytest.raises(RuntimeError, match="HTTP 404"):
            await store.download_model(model, client=client)


async def test_runtime_with_wrong_checksum_is_rejected_and_not_installed(voice_home, monkeypatch):
    archive = _zip_bytes({"piper/piper.exe": b"tampered"})
    win = dataclasses.replace(runtime_for("tts", "win"), sha256="0" * 64)
    monkeypatch.setattr(store, "runtime_for", lambda kind, *_: win)
    async with _mock_client({win.url: archive}) as client:
        with pytest.raises(RuntimeError, match="sha256"):
            await store.ensure_runtime("tts", client=client)
    assert store.find_runtime_executable("tts", win) is None


def test_runtime_catalog_pins_sha256_for_every_downloadable_runtime():
    for key in ("win", "mac-arm", "mac-x64", "linux-x64", "linux-arm"):
        for kind in ("tts", "stt"):
            runtime = runtime_for(kind, key)
            assert runtime.url is None or len(runtime.sha256) == 64, (kind, key)
    assert runtime_for("tts", "linux-x64").path_names == ()      # không dò nhầm `piper` của libratbag


def test_svg_with_huge_declared_size_is_clamped_and_external_images_dropped():
    get_qapp()
    from src.ui.rich_content.svg_figure_image_renderer import MAX_FIGURE_HEIGHT, render_svg_png
    _png, width, height = render_svg_png('<svg width="10" height="10000000"><rect width="10" height="10"/></svg>', 340)
    assert height <= MAX_FIGURE_HEIGHT + 16 and width >= 1
    from src.ui.rich_content import svg_figure_image_renderer as svg_mod
    cleaned = svg_mod._EXTERNAL_IMAGE_RE.sub("", '<svg><image href="file:///C:/secret.png"/><image href="data:image/png;base64,AA"/></svg>')
    assert "file:" not in cleaned and "data:image/png" in cleaned


def test_overlong_latex_uses_unicode_fallback_without_rendering():
    from src.ui.rich_content.latex_math_image_renderer import math_html
    assert "<img" not in math_html("x+" * 300, display=False)
    assert "<img" not in math_html("{" * 20 + "x" + "}" * 20, display=False)


def test_safe_extract_rejects_path_traversal(tmp_path):
    archive = tmp_path / "evil.zip"
    archive.write_bytes(_zip_bytes({"../escape.txt": b"x"}))
    with pytest.raises(RuntimeError, match="không an toàn"):
        store._safe_extract(archive, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


async def test_mac_stt_without_prebuilt_runtime_raises_manual_hint(voice_home, monkeypatch):
    monkeypatch.setattr(store, "runtime_for", lambda kind, *_: runtime_for(kind, "mac-arm"))
    with pytest.raises(RuntimeError, match="brew install whisper-cpp"):
        await store.ensure_runtime("stt")


# ---------------- 3. engines & settings ----------------
async def test_offline_tts_engine_runs_piper_with_model_and_speed(voice_home, monkeypatch):
    model = get_model("piper-vi-vais1000-medium")
    exe = _fake_install(model)
    assert is_embedded_tts_available()
    calls = {}

    def fake_run(cmd, input=None, **kw):
        calls["cmd"], calls["input"] = cmd, input
        Path(cmd[cmd.index("--output_file") + 1]).write_bytes(b"RIFF....WAVE")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    wav = await LocalEmbeddedTTSEngine().synthesize("Xin chào các bạn", "", speed=1.25)
    assert wav.startswith(b"RIFF")
    assert calls["cmd"][0] == str(exe) and str(store.model_main_path(model)) in calls["cmd"]
    assert calls["cmd"][calls["cmd"].index("--length_scale") + 1] == "0.80"
    assert calls["input"] == "Xin chào các bạn.".encode("utf-8")   # Piper tự chuẩn hoá dấu câu (câu có dấu kết thúc)


async def test_offline_tts_without_download_gives_friendly_error(voice_home):
    with pytest.raises(RuntimeError, match="Tải giọng đọc offline"):
        await LocalEmbeddedTTSEngine().synthesize("Xin chào", "", 1.0)


async def test_offline_stt_engine_parses_whisper_cli_output(voice_home, monkeypatch):
    model = get_model("whisper-small-q5")
    _fake_install(model)

    def fake_run(cmd, **kw):
        assert cmd[cmd.index("-l") + 1] == "vi" and str(store.model_main_path(model)) in cmd
        return subprocess.CompletedProcess(cmd, 0, " Xin chào\n[00:00:01.000 --> 00:00:02.000]  Ted ơi\n".encode(), b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert await LocalEmbeddedSTTEngine("").transcribe(b"RIFFdata", language="vi") == "Xin chào Ted ơi"


def test_settings_persist_stt_and_offline_model_fields(tmp_path):
    cfg = AppConfig(data_dir=tmp_path)
    cfg.stt_enabled, cfg.stt_mode, cfg.stt_language = True, "embedded", "en"
    cfg.stt_local_model, cfg.tts_local_voice_vi = "whisper-small-q5", "piper-vi-vais1000-medium"
    cfg.save()
    again = AppConfig(data_dir=tmp_path)
    assert (again.stt_enabled, again.stt_mode, again.stt_language) == (True, "embedded", "en")
    assert again.stt_local_model == "whisper-small-q5" and again.tts_local_voice_vi == "piper-vi-vais1000-medium"


# ---------------- 4. UI ----------------
def test_server_preset_fills_tts_inputs_without_saving(voice_home, monkeypatch):
    get_qapp()
    from src.core.voice_config_presets import get_preset
    from src.ui.dashboard_tabs.tts_settings_group_widget import TtsSettingsGroupWidget
    saved = []
    monkeypatch.setattr(settings, "save", lambda: saved.append(1))
    widget = TtsSettingsGroupWidget()
    widget.apply_preset(get_preset("tts-edge-male"))
    assert widget.current_mode() == "server" and widget.chk_enabled.isChecked()
    assert widget.txt_url.text() == "http://127.0.0.1:5050/v1"
    assert widget.combo_voice_vi.currentText() == "vi-VN-NamMinhNeural"
    assert widget.spin_speed.value() == pytest.approx(0.95)
    assert "Nam Minh" in widget.lbl_status.text() and saved == []


def test_offline_preset_asks_to_download_missing_then_prefills_after_download(voice_home, monkeypatch):
    get_qapp()
    from src.core.voice_config_presets import get_preset
    from src.ui.dashboard_tabs.tts_settings_group_widget import TtsSettingsGroupWidget
    asked, opened = [], []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.Yes)
    widget = TtsSettingsGroupWidget()
    monkeypatch.setattr(widget, "open_download_dialog", lambda ids=(): opened.append(list(ids)))
    widget.apply_preset(get_preset("tts-offline-english-listening"))
    assert widget.current_mode() == "embedded" and asked
    assert set(opened[0]) == {"piper-vi-vais1000-medium", "piper-en-ryan-medium"}

    for mid in opened[0]:
        _fake_install(get_model(mid))
    widget._on_models_ready(opened[0])
    assert widget.combo_local_vi.currentData() == "piper-vi-vais1000-medium"
    assert widget.combo_local_en.currentData() == "piper-en-ryan-medium"
    widget.apply_to_settings()
    assert settings.tts_mode == "embedded" and settings.tts_local_voice_en == "piper-en-ryan-medium"


def test_stt_group_prefills_downloaded_model_and_saves(voice_home):
    get_qapp()
    from src.ui.dashboard_tabs.stt_settings_group_widget import SttSettingsGroupWidget
    widget = SttSettingsGroupWidget()
    _fake_install(get_model("whisper-base-q5"))
    widget._on_models_ready(["whisper-base-q5"])
    assert widget.current_mode() == "embedded" and widget.combo_local_model.currentData() == "whisper-base-q5"
    widget.apply_to_settings()
    assert settings.stt_enabled and settings.stt_local_model == "whisper-base-q5"


def test_preset_picker_dialog_filters_and_emits_selected(voice_home):
    get_qapp()
    from src.ui.dashboard_tabs.voice_preset_picker_dialog import VoicePresetPickerDialog
    dialog = VoicePresetPickerDialog("stt")
    assert dialog.selected_preset().recommended   # mặc định chọn sẵn mẫu ⭐
    dialog.search.setText("groq")
    assert dialog.lbl_count.text() == "1 mẫu" and dialog.selected_preset().id == "stt-groq-turbo"
    assert "API key" in dialog.detail.text()
    chosen = []
    dialog.preset_chosen.connect(chosen.append)
    dialog.btn_apply.click()
    assert [p.id for p in chosen] == ["stt-groq-turbo"]


async def test_download_dialog_preselects_downloads_and_shows_guide(voice_home, monkeypatch):
    get_qapp()
    from src.ui.dashboard_tabs import offline_voice_model_download_dialog as dlg_mod
    dialog = dlg_mod.OfflineVoiceModelDownloadDialog("tts", ["piper-en-amy-medium"])
    assert [m.id for m in dialog.selected_models()] == ["piper-en-amy-medium"]

    async def fake_download(model, progress=None, cancel=None, client=None):
        progress(10, 10, model.title)
        _fake_install(model)
        return store.model_main_path(model)

    monkeypatch.setattr(dlg_mod, "download_model", fake_download)
    ready = []
    dialog.models_ready.connect(ready.append)
    assert await dialog.run_downloads(dialog.selected_models()) == ["piper-en-amy-medium"]
    assert ready == [["piper-en-amy-medium"]]
    assert "Tải xong" in dialog.done_panel.text() and not dialog.done_panel.isHidden()
    assert not dialog.btn_test.isHidden()
