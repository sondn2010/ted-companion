"""VieNeu-TTS (phase 01-02): catalog + uv pin theo HĐH, installer (lệnh uv, huỷ, idempotent), định tuyến engine TTS.
Không dùng mạng, không cài thật: lệnh con và tải uv được thay bằng bản giả."""

import asyncio
import json
import sys
import threading

import httpx
import pytest

from src.config import settings
from src.core import offline_voice_model_store as store
from src.core import vieneu_runtime_installer as installer
from src.core.offline_voice_model_catalog import OFFLINE_VOICE_MODELS, get_model, runtime_for
from src.core.tts_service import LocalEmbeddedTTSEngine, is_embedded_tts_available
from src.core.vieneu_runtime_paths import sidecar_script_path, venv_python
from src.core.vieneu_sidecar_process_manager import SidecarEndpoint
from src.core.vieneu_sidecar_tts_engine import VieneuSidecarTTSEngine


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(store.shutil, "which", lambda _n: None)
    monkeypatch.setattr(settings, "vieneu_voices", {})
    return tmp_path


@pytest.fixture
def fake_install_env(home, monkeypatch):
    """uv giả + bộ chạy lệnh giả: lệnh `uv venv` tạo python giả, ghi lại mọi lệnh."""
    calls: list[list[str]] = []

    async def fake_ensure_runtime(kind, progress=None, cancel=None, client=None):
        return home / "uv"

    def fake_run(cmd, env, log_file, cancel, timeout_s=0):
        calls.append(cmd)
        assert env["HF_HOME"].startswith(str(home)) and env["UV_PYTHON_INSTALL_DIR"].startswith(str(home))
        if "venv" in cmd[:2]:
            venv_python().parent.mkdir(parents=True, exist_ok=True)
            venv_python().write_text("py")

    monkeypatch.setattr(installer, "check_env_path_length", lambda: None)   # tmp_path của pytest trên Windows có thể > 100 ký tự
    monkeypatch.setattr(installer, "ensure_runtime", fake_ensure_runtime)
    monkeypatch.setattr(installer, "run_logged_command", fake_run)
    return calls


# ---------------- catalog ----------------
def test_vieneu_catalog_entries_and_piper_default_engine():
    turbo, nano = get_model("vieneu-v3-turbo"), get_model("vieneu-v3-nano")
    assert turbo.engine == nano.engine == "vieneu" and turbo.kind == "tts" and turbo.language == "vi"
    assert turbo.recommended and turbo.quality == 5 and not nano.recommended
    assert all(m.engine == "piper" for m in OFFLINE_VOICE_MODELS if m.id.startswith("piper-"))


@pytest.mark.parametrize("key,suffix,exe", [
    ("win", "x86_64-pc-windows-msvc.zip", "uv.exe"), ("mac-arm", "aarch64-apple-darwin.tar.gz", "uv"),
    ("mac-x64", "x86_64-apple-darwin.tar.gz", "uv"), ("linux-x64", "x86_64-unknown-linux-gnu.tar.gz", "uv"),
    ("linux-arm", "aarch64-unknown-linux-gnu.tar.gz", "uv"),
])
def test_uv_runtime_pinned_per_os_with_sha256(key, suffix, exe):
    rt = runtime_for("vieneu", key)
    assert rt.url.startswith("https://github.com/astral-sh/uv/releases/download/0.12.23/uv-") and rt.url.endswith(suffix)
    assert rt.executable == exe and len(rt.sha256) == 64


# ---------------- installer ----------------
def test_install_runs_uv_venv_pip_then_warmup_and_is_idempotent(fake_install_env):
    model, progress = get_model("vieneu-v3-nano"), []
    assert not store.is_model_installed(model)
    asyncio.run(store.download_model(model, lambda d, t, label: progress.append(label)))
    venv_cmd, pip_cmd, warm_cmd = fake_install_env
    assert venv_cmd[1:5] == ["venv", "--managed-python", "--python", "3.12"]
    assert pip_cmd[1:3] == ["pip", "install"] and pip_cmd[-1] == "vieneu==3.8.3" and str(venv_python()) in pip_cmd
    assert warm_cmd[0] == str(venv_python()) and warm_cmd[1] == str(sidecar_script_path()) and "--warmup" in warm_cmd
    assert warm_cmd[warm_cmd.index("--mode") + 1] == "nano"
    assert store.is_model_installed(model) and installer.is_vieneu_installed("vieneu-v3-nano")
    assert [p[:5] for p in progress if p.startswith("[")] == ["[1/4]", "[2/4]", "[3/4]", "[4/4]"]
    fake_install_env.clear()
    asyncio.run(installer.install_vieneu(model))
    assert fake_install_env == []   # đã cài → không chạy lại gì


def test_second_model_reuses_venv_and_package(fake_install_env):
    asyncio.run(installer.install_vieneu(get_model("vieneu-v3-nano")))
    fake_install_env.clear()
    asyncio.run(installer.install_vieneu(get_model("vieneu-v3-turbo")))
    assert len(fake_install_env) == 1 and "--warmup" in fake_install_env[0]


def test_cancel_during_pip_removes_venv_and_leaves_no_marker(fake_install_env, monkeypatch):
    def cancelling_run(cmd, env, log_file, cancel, timeout_s=0):
        if "venv" in cmd[:2]:
            venv_python().parent.mkdir(parents=True, exist_ok=True)
            venv_python().write_text("py")
        else:
            raise store.DownloadCancelled()

    monkeypatch.setattr(installer, "run_logged_command", cancelling_run)
    model = get_model("vieneu-v3-turbo")
    with pytest.raises(store.DownloadCancelled):
        asyncio.run(installer.install_vieneu(model))
    assert not venv_python().exists() and not store.is_model_installed(model)


def test_uninstall_removes_env_only_when_last_model_gone(fake_install_env):
    for mid in ("vieneu-v3-nano", "vieneu-v3-turbo"):
        asyncio.run(installer.install_vieneu(get_model(mid)))
    installer.uninstall_vieneu("vieneu-v3-nano")
    assert not store.is_model_installed(get_model("vieneu-v3-nano")) and venv_python().exists()
    store.delete_model(get_model("vieneu-v3-turbo"))
    assert not venv_python().exists() and not installer.is_vieneu_installed("vieneu-v3-turbo")


def test_run_logged_command_logs_fails_and_cancels(tmp_path):
    log = tmp_path / "logs" / "x.log"
    installer.run_logged_command([sys.executable, "-c", "print('hello-log')"], {}, log, None)
    assert "hello-log" in log.read_text(encoding="utf-8")
    with pytest.raises(RuntimeError, match="mã 3"):
        installer.run_logged_command([sys.executable, "-c", "import sys; sys.exit(3)"], {}, log, None)

    async def scenario():
        cancel = asyncio.Event()
        threading.Timer(0.5, cancel.set).start()
        await asyncio.to_thread(installer.run_logged_command,
                                [sys.executable, "-c", "import time; time.sleep(60)"], {}, log, cancel)
    with pytest.raises(store.DownloadCancelled):
        asyncio.run(scenario())


# ---------------- routing ----------------
def _mark_installed(model_id):
    model = get_model(model_id)
    d = store.model_dir(model)
    d.mkdir(parents=True, exist_ok=True)
    (d / model.main_file).write_text("{}")


def test_auto_pick_prefers_vieneu_turbo_over_piper_when_both_installed(home):
    """Bug thật: giọng Việt để "Tự chọn" + đã tải cả Piper VAIS1000 lẫn VieNeu Turbo (đều khuyên dùng)
    → trước đây lấy Piper vì đứng trước trong catalog; giờ chọn bản chất lượng cao hơn."""
    piper = get_model("piper-vi-vais1000-medium")
    d = store.model_dir(piper)
    d.mkdir(parents=True, exist_ok=True)
    for _url, name in piper.files:
        (d / name).write_text("{}")
    assert store.resolve_model("tts", "", "vi").id == piper.id
    _mark_installed("vieneu-v3-turbo")
    assert store.resolve_model("tts", "", "vi").id == "vieneu-v3-turbo"
    assert store.resolve_model("tts", piper.id, "vi").id == piper.id   # người dùng chọn rõ Piper thì vẫn giữ


def test_vieneu_installed_counts_as_embedded_available_without_piper(home):
    assert not is_embedded_tts_available()
    _mark_installed("vieneu-v3-nano")
    assert is_embedded_tts_available()


def test_embedded_engine_routes_vieneu_model_to_sidecar_engine_and_piper_unchanged(home, monkeypatch):
    seen = {}

    async def fake_sidecar(self, text, voice, speed=1.0, http_client=None, should_continue=None, on_chunk=None):
        seen.update(model=self.model_id, text=text, speed=speed)
        return b"RIFFfake"

    monkeypatch.setattr(VieneuSidecarTTSEngine, "synthesize", fake_sidecar)
    _mark_installed("vieneu-v3-turbo")
    out = asyncio.run(LocalEmbeddedTTSEngine().synthesize("xin chào", "vieneu-v3-turbo", 1.2))
    assert out == b"RIFFfake" and seen == {"model": "vieneu-v3-turbo", "text": "xin chào", "speed": 1.2}
    # Piper đã cài nhưng thiếu binary → vẫn báo lỗi Piper như cũ, không đụng sidecar
    piper = get_model("piper-vi-vais1000-medium")
    store.model_dir(piper).mkdir(parents=True)
    for _u, name in piper.files:
        (store.model_dir(piper) / name).write_text("x")
    seen.clear()
    with pytest.raises(RuntimeError, match="bộ chạy"):
        asyncio.run(LocalEmbeddedTTSEngine().synthesize("xin chào", piper.id, 1.0))
    assert seen == {}


class _FakeManager:
    def ensure_running(self, model_id, precision="fp32"):
        return SidecarEndpoint("http://127.0.0.1:5555/v1", "tok123", model_id)


def test_sidecar_engine_calls_local_openai_endpoint_with_token_and_settings_voice(home, monkeypatch):
    monkeypatch.setattr(settings, "vieneu_voices", {"vieneu-v3-turbo": "Mai Anh", "vieneu-v3-nano": "Khác"})
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(url=str(request.url), auth=request.headers["authorization"], body=json.loads(request.content))
        return httpx.Response(200, content=b"RIFFxxxx")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    engine = VieneuSidecarTTSEngine("vieneu-v3-turbo", manager=_FakeManager())
    assert asyncio.run(engine.synthesize("chào", "vieneu-v3-turbo", 1.1, http_client=client)) == b"RIFFxxxx"
    assert captured["url"] == "http://127.0.0.1:5555/v1/audio/speech" and captured["auth"] == "Bearer tok123"
    assert captured["body"]["voice"] == "Mai Anh" and captured["body"]["input"] == "chào."   # bộ tiền xử lý thêm dấu kết câu


async def test_prewarm_starts_sidecar_only_when_vieneu_is_the_vi_voice(home, monkeypatch):
    from src.core.vieneu_sidecar_tts_engine import prewarm_vieneu_if_selected
    started = []

    class Mgr:
        def ensure_running(self, model_id, precision="fp32"):
            started.append(model_id)

    monkeypatch.setattr(settings, "tts_enabled", True, raising=False)
    monkeypatch.setattr(settings, "tts_mode", "embedded", raising=False)
    monkeypatch.setattr(settings, "tts_local_voice_vi", "", raising=False)
    assert await prewarm_vieneu_if_selected(Mgr()) is False   # chưa cài VieNeu
    _mark_installed("vieneu-v3-turbo")
    assert await prewarm_vieneu_if_selected(Mgr()) is True
    assert started == ["vieneu-v3-turbo"]
    monkeypatch.setattr(settings, "tts_enabled", False, raising=False)
    assert await prewarm_vieneu_if_selected(Mgr()) is False   # tắt đọc giọng → không tốn RAM nạp model
    assert started == ["vieneu-v3-turbo"]
