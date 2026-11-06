"""Regression cho các lỗi review VieNeu: proxy loopback (H1), giọng theo model (H2), đọc văn bản dài theo khúc (H3),
chuỗi cung ứng/offline (H4, M4), stop không treo UI (M1), gỡ cài đặt an toàn (M2), cache giọng (M3), picker (M5),
READY/token/nonce (M6), sidecar treo (M7), kill cả cây tiến trình."""

import asyncio
import importlib.util
import io
import json
import os
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from PySide6.QtWidgets import QWidget

from qt_offscreen_app_helper import flush_qt_garbage, get_qapp

from src.config import settings
from src.core import offline_voice_model_store as store
from src.core import vieneu_runtime_installer as installer
from src.core import vieneu_runtime_paths as paths
from src.core import vieneu_sidecar_process_manager as pm
from src.core.offline_voice_model_catalog import VIENEU_MARKER_FILE, get_model
from src.core.vieneu_installer_command_runner import kill_process_tree
from src.core.vieneu_sidecar_tts_engine import VieneuSidecarTTSEngine, list_vieneu_voices
from src.core.vieneu_text_chunking_and_wav_concat import concat_wav_bytes, split_text_for_tts
from src.ui.dashboard_tabs import vieneu_voice_picker_widget as picker_mod
from src.ui.dashboard_tabs.vieneu_voice_picker_widget import VieneuVoicePickerWidget

_SIDECAR_DIR = paths.sidecar_script_path().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _SIDECAR_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(_SIDECAR_DIR))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(_SIDECAR_DIR))
    return mod


sidecar = _load("vieneu_sidecar_review", "vieneu_openai_speech_sidecar.py")
pins = _load("vieneu_pins_review", "vieneu_hf_revision_pins.py")


def _wav(frames: int, rate: int = 24000, value: int = 0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(value.to_bytes(2, "little", signed=True) * frames)
    return buf.getvalue()


class FakeVieneu:
    sample_rate = 24000
    _default_voice = "Adam"

    def __init__(self):
        self.calls = []

    def list_preset_voices(self):
        return [("Adam", "Adam"), ("Mai Anh", "Mai Anh")]

    def infer(self, text, **kwargs):
        self.calls.append((text, kwargs))
        import numpy as np
        return np.zeros(2400, dtype=np.float32)


@pytest.fixture
def real_server():
    srv = sidecar.build_server(sidecar.SpeechService(FakeVieneu(), "nano"), 0, "secret")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


# ---------------- H1: loopback không qua proxy ----------------
def test_health_probe_and_engine_bypass_proxy_env(real_server, monkeypatch):
    for key in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(key, "http://127.0.0.1:9")   # proxy chết: đi qua proxy là hỏng
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    assert pm._probe_health(real_server, "secret")

    class Mgr:
        def ensure_running(self, model_id, precision="fp32"):
            return pm.SidecarEndpoint(f"http://127.0.0.1:{real_server}/v1", "secret", model_id)

    out = asyncio.run(VieneuSidecarTTSEngine("vieneu-v3-nano", manager=Mgr()).synthesize("xin chào", "", 1.0))
    assert out[:4] == b"RIFF"


# ---------------- M6: nonce HMAC, không lộ token cho tiến trình lạ ----------------
def test_probe_rejects_impostor_without_or_with_wrong_proof(real_server):
    assert not pm._probe_health(real_server, "wrong-token")   # sidecar thật nhưng khác token → proof sai

    class Impostor(BaseHTTPRequestHandler):
        seen_auth = []

        def do_GET(self):
            Impostor.seen_auth.append(self.headers.get("Authorization"))
            body = b'{"status": "ok"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Impostor)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert not pm._probe_health(srv.server_address[1], "secret")
        assert Impostor.seen_auth == [None]   # token không bao giờ được gửi đi khi dò sức khoẻ
    finally:
        srv.shutdown()
        srv.server_close()


# ---------------- H2: giọng theo model + rơi về mặc định ----------------
def test_sidecar_unknown_voice_falls_back_to_default_instead_of_400():
    fake = FakeVieneu()
    sidecar.SpeechService(fake, "nano").synthesize("a", "Giọng-của-model-khác", None)
    assert fake.calls == [("a", {})]
    fake.calls.clear()
    sidecar.SpeechService(fake, "nano").synthesize("a", "Mai Anh", None)
    assert fake.calls == [("a", {"voice": "Mai Anh"})]


def test_legacy_single_voice_migrates_to_selected_vieneu_model_else_turbo(tmp_path, monkeypatch):
    for local_voice, key in (("vieneu-v3-nano", "vieneu-v3-nano"), ("piper-vi", "vieneu-v3-turbo")):
        (tmp_path / "settings.json").write_text(
            json.dumps({"vieneu_voice": "Mai Anh", "tts_local_voice_vi": local_voice}), encoding="utf-8")
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        monkeypatch.setattr(settings, "settings_file", tmp_path / "settings.json", raising=False)
        settings.load()
        assert settings.vieneu_voices == {key: "Mai Anh"}
    settings.save()
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert "vieneu_voice" not in saved and saved["vieneu_voices"] == {"vieneu-v3-turbo": "Mai Anh"}


def test_engine_uses_voice_of_its_own_model(monkeypatch):
    monkeypatch.setattr(settings, "vieneu_voices", {"vieneu-v3-turbo": "A", "vieneu-v3-nano": "B"})
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content)["voice"])
        return httpx.Response(200, content=b"RIFFx")

    class Mgr:
        def ensure_running(self, model_id, precision="fp32"):
            return pm.SidecarEndpoint("http://127.0.0.1:1/v1", "t", model_id)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    for model in ("vieneu-v3-nano", "vieneu-v3-turbo"):
        asyncio.run(VieneuSidecarTTSEngine(model, manager=Mgr()).synthesize("x", "", 1.0, http_client=client))
    assert bodies == ["B", "A"]


# ---------------- H3: chia khúc, ghép WAV, dừng giữa chừng ----------------
def test_split_text_groups_sentences_then_commas_then_hard():
    text = " ".join(f"Câu số {i} dài vừa phải để thử." for i in range(40))
    chunks = split_text_for_tts(text)
    assert len(chunks) > 1 and all(len(c) <= 350 for c in chunks)
    assert " ".join(chunks) == text   # không mất/sai chữ nào
    comma = ", ".join(["mệnh đề khá dài số một hai ba"] * 30)   # 1 câu duy nhất, chỉ có dấu phẩy
    assert all(len(c) <= 350 for c in split_text_for_tts(comma)) and len(split_text_for_tts(comma)) > 1
    hard = "x" * 1000   # không khoảng trắng, không dấu câu
    assert [len(c) for c in split_text_for_tts(hard)] == [350, 350, 300]
    assert split_text_for_tts("  \n ") == [] and split_text_for_tts("Chào bạn.") == ["Chào bạn."]


def test_concat_wav_parses_riff_and_rejects_format_mismatch():
    out = concat_wav_bytes([_wav(100, value=1), _wav(50, value=2)])
    with wave.open(io.BytesIO(out)) as wf:
        assert (wf.getframerate(), wf.getnchannels(), wf.getsampwidth(), wf.getnframes()) == (24000, 1, 2, 150)
    with pytest.raises(ValueError, match="khác định dạng"):
        concat_wav_bytes([_wav(10), _wav(10, rate=48000)])
    with pytest.raises(ValueError):
        concat_wav_bytes([_wav(10), b"not a wav at all"])
    # WAV có chunk phụ (LIST, lẻ byte) trước data + kích thước data placeholder kiểu stream
    base = _wav(10)
    fmt_end = 12 + 8 + 16
    extra = b"LIST" + (3).to_bytes(4, "little") + b"abc" + b"\x00"
    streamy = base[:fmt_end] + extra + b"data" + b"\xff\xff\xff\xff" + base[fmt_end + 8:]
    with wave.open(io.BytesIO(concat_wav_bytes([base, streamy]))) as wf:
        assert wf.getnframes() == 20
    assert concat_wav_bytes([b"RIFFxyz"]) == b"RIFFxyz"   # 1 khúc: trả nguyên


def test_engine_chunks_long_text_concats_and_aborts_when_superseded(monkeypatch):
    monkeypatch.setattr(settings, "vieneu_voices", {})
    sent = []

    def handler(request):
        sent.append(json.loads(request.content)["input"])
        return httpx.Response(200, content=_wav(100))

    class Mgr:
        def ensure_running(self, model_id, precision="fp32"):
            return pm.SidecarEndpoint("http://127.0.0.1:1/v1", "t", model_id)

    text = " ".join(f"Đây là câu số {i} khá là dài để thử cắt khúc." for i in range(40))
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    engine = VieneuSidecarTTSEngine("vieneu-v3-nano", manager=Mgr())
    out = asyncio.run(engine.synthesize(text, "", 1.0, http_client=client))
    assert len(sent) > 1 and all(len(c) <= 350 for c in sent) and " ".join(sent) == text
    with wave.open(io.BytesIO(out)) as wf:   # mỗi câu 11 từ → nghỉ 0.35 s sau mỗi khúc trừ khúc cuối
        assert wf.getnframes() == 100 * len(sent) + round(0.35 * 24000) * (len(sent) - 1)
    sent.clear()
    allowed = iter([True, False])   # khúc đầu được đọc, sau đó bị stop()/câu mới thay
    assert asyncio.run(engine.synthesize(text, "", 1.0, http_client=client, should_continue=lambda: next(allowed))) == b""
    assert len(sent) == 1


def test_engine_streams_each_chunk_via_on_chunk_as_soon_as_ready(monkeypatch):
    """Phát sớm: mỗi khúc được giao ngay sau khi tổng hợp xong, trước khi khúc kế được gửi đi."""
    monkeypatch.setattr(settings, "vieneu_voices", {})
    timeline = []

    def handler(request):
        timeline.append(("request", json.loads(request.content)["input"][:12]))
        return httpx.Response(200, content=_wav(100))

    class Mgr:
        def ensure_running(self, model_id, precision="fp32"):
            return pm.SidecarEndpoint("http://127.0.0.1:1/v1", "t", model_id)

    text = " ".join(f"Đây là câu số {i} khá là dài để thử cắt khúc." for i in range(40))
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    engine = VieneuSidecarTTSEngine("vieneu-v3-turbo", manager=Mgr())
    out = asyncio.run(engine.synthesize(
        text, "", 1.0, http_client=client, on_chunk=lambda wav: timeline.append(("play", len(wav)))))
    assert out == b""
    kinds = [k for k, _ in timeline]
    assert kinds[:2] == ["request", "play"] and kinds.count("play") == kinds.count("request") > 1
    assert all(a != b for a, b in zip(kinds, kinds[1:]))   # xen kẽ: tổng hợp → giao → tổng hợp → giao


def test_tts_service_passes_generation_check_to_engine(monkeypatch):
    from src.core.tts_service import TTSService
    seen = {}

    class Engine:
        async def synthesize(self, text, voice, speed=1.0, http_client=None, should_continue=None, on_chunk=None):
            seen["before"] = should_continue()
            svc.stop()   # người dùng bấm dừng giữa lúc đọc
            seen["after"] = should_continue()
            return b""

    get_qapp()
    svc = TTSService()
    monkeypatch.setattr(settings, "tts_enabled", True)
    monkeypatch.setattr(svc, "get_engine", lambda *a, **k: Engine())
    asyncio.run(svc.speak("Xin chào các bạn", lang="vi"))
    assert seen == {"before": True, "after": False}


# ---------------- process manager (tiến trình giả) ----------------
class FakeProc:
    def __init__(self, stdout: bytes = b"READY port=4321\n", dies=False):
        self.stdout = io.BytesIO(stdout)
        self.dead, self.killed = dies, False
        self.env = None

    def poll(self):
        return 1 if self.dead else None

    def kill(self):
        self.dead = self.killed = True

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def env_home(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    paths.venv_python().parent.mkdir(parents=True)
    paths.venv_python().write_text("py")
    (paths.vieneu_env_dir() / paths.PKG_MARKER_NAME).write_text(paths.VIENEU_PACKAGE_SPEC)
    monkeypatch.setattr(store.shutil, "which", lambda _n: None)
    return tmp_path


def _manager(spawned):
    def popen(cmd, **kwargs):
        proc = FakeProc()
        proc.cmd, proc.env = cmd, kwargs["env"]
        spawned.append(proc)
        return proc

    return pm.VieneuSidecarManager(popen=popen, probe=lambda port, token: True, startup_timeout=2)


def test_manager_reads_ready_port_passes_token_by_env_and_restarts(env_home):
    spawned = []
    mgr = _manager(spawned)
    ep = mgr.ensure_running("vieneu-v3-nano")
    proc = spawned[0]
    assert ep.base_url == "http://127.0.0.1:4321/v1"   # cổng do sidecar tự báo qua stdout
    assert "--token" not in proc.cmd and ep.token not in " ".join(proc.cmd)   # token không nằm trên argv
    assert proc.env[pm.TOKEN_ENV] == ep.token and proc.cmd[proc.cmd.index("--port") + 1] == "0"
    assert proc.env["HF_HUB_OFFLINE"] == "1" and proc.env["TRANSFORMERS_OFFLINE"] == "1"   # M4
    assert mgr.ensure_running("vieneu-v3-nano") is ep and len(spawned) == 1
    mgr.ensure_running("vieneu-v3-turbo")
    assert len(spawned) == 2 and proc.killed
    spawned[1].dead = True
    mgr.ensure_running("vieneu-v3-turbo")
    assert len(spawned) == 3
    mgr.stop()
    assert spawned[2].killed and not mgr.is_running()


def test_manager_errors(env_home):
    spawned = []
    mgr = _manager(spawned)
    with pytest.raises(ValueError):
        mgr.ensure_running("piper-vi-vais1000-medium")
    early = pm.VieneuSidecarManager(popen=lambda cmd, **kw: FakeProc(b"Traceback boom\n", dies=True),
                                    probe=lambda p, t: False, startup_timeout=2)
    with pytest.raises(RuntimeError, match="thoát sớm"):
        early.ensure_running("vieneu-v3-nano")
    hung = pm.VieneuSidecarManager(popen=lambda cmd, **kw: FakeProc(b""), probe=lambda p, t: False, startup_timeout=0.4)
    with pytest.raises(RuntimeError, match="không phản hồi"):
        hung.ensure_running("vieneu-v3-nano")
    assert not hung.is_running()
    (paths.vieneu_env_dir() / paths.PKG_MARKER_NAME).unlink()   # M2: có python nhưng thiếu file đánh dấu = hỏng
    with pytest.raises(RuntimeError, match="Chưa cài"):
        mgr.ensure_running("vieneu-v3-nano")


def test_manager_single_start_in_flight(env_home):
    spawned, results = [], []
    mgr = _manager(spawned)
    threads = [threading.Thread(target=lambda: results.append(mgr.ensure_running("vieneu-v3-nano"))) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(spawned) == 1 and len({r.token for r in results}) == 1


def test_stop_does_not_block_behind_inflight_start(env_home):
    """M1: stop() (UI thread) trả về ngay dù ensure_running đang chờ sidecar nạp model."""
    spawned = []
    mgr = pm.VieneuSidecarManager(popen=lambda cmd, **kw: spawned.append(FakeProc(b"")) or spawned[-1],
                                  probe=lambda p, t: False, startup_timeout=30)
    errors = []

    def starter():
        try:
            mgr.ensure_running("vieneu-v3-nano")
        except RuntimeError as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=starter)
    thread.start()
    deadline = time.monotonic() + 5
    while not spawned and time.monotonic() < deadline:
        time.sleep(0.01)
    t0 = time.monotonic()
    mgr.stop()
    assert time.monotonic() - t0 < 1.0 and spawned[0].killed
    thread.join(timeout=5)
    assert not thread.is_alive() and errors and "dừng" in errors[0]


def test_unhealthy_endpoint_is_killed_and_respawned_but_stale_one_ignored(env_home):
    spawned = []
    mgr = _manager(spawned)
    ep = mgr.ensure_running("vieneu-v3-nano")
    mgr.mark_unhealthy(pm.SidecarEndpoint(ep.base_url, "other", ep.model_id))   # endpoint cũ/khác → bỏ qua
    assert not spawned[0].killed
    mgr.mark_unhealthy(ep)
    assert spawned[0].killed
    assert mgr.ensure_running("vieneu-v3-nano") is not ep and len(spawned) == 2


def test_engine_timeout_marks_sidecar_unhealthy(monkeypatch):
    marked = []

    class Mgr:
        ep = pm.SidecarEndpoint("http://127.0.0.1:1/v1", "t", "vieneu-v3-nano")

        def ensure_running(self, model_id, precision="fp32"):
            return self.ep

        def mark_unhealthy(self, endpoint):
            marked.append(endpoint)

    def handler(request):
        raise httpx.ReadTimeout("treo", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(VieneuSidecarTTSEngine("vieneu-v3-nano", manager=Mgr()).synthesize("xin chào", "", 1.0, http_client=client))
    assert marked == [Mgr.ep]


# ---------------- M2: gỡ cài đặt ----------------
def test_uninstall_blocks_restart_removes_marker_first(env_home, monkeypatch):
    model = get_model("vieneu-v3-nano")
    marker = store.model_dir(model) / VIENEU_MARKER_FILE
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}")
    from src.core.vieneu_sidecar_process_manager import vieneu_sidecar_manager as mgr
    observed = {}
    real_rmtree = installer.shutil.rmtree

    def spying_rmtree(path, *a, **k):
        if "marker_gone" not in observed and str(path) == str(paths.vieneu_env_dir()):
            observed["marker_gone"] = not (paths.vieneu_env_dir() / paths.PKG_MARKER_NAME).exists()
        try:
            mgr.ensure_running("vieneu-v3-nano")   # speak/picker xen vào lúc đang xoá
        except RuntimeError as exc:
            observed["restart"] = str(exc)
        real_rmtree(path, *a, **k)

    monkeypatch.setattr(installer.shutil, "rmtree", spying_rmtree)
    asyncio.run(installer.uninstall_vieneu_async("vieneu-v3-nano"))
    assert observed["marker_gone"] and "gỡ cài đặt" in observed["restart"]
    assert not paths.venv_is_usable() and mgr._disabled == 0   # xong → cho phép lại


def test_installer_rebuilds_half_deleted_venv_and_pins_exclude_newer(env_home, monkeypatch):
    calls = []

    async def fake_runtime(*_a, **_k):
        return env_home / "uv"

    def fake_run(cmd, env, log_file, cancel, timeout_s=0):
        calls.append(cmd)
        if "venv" in cmd[:2]:
            paths.venv_python().parent.mkdir(parents=True, exist_ok=True)
            paths.venv_python().write_text("py")

    monkeypatch.setattr(installer, "check_env_path_length", lambda: None)
    monkeypatch.setattr(installer, "ensure_runtime", fake_runtime)
    monkeypatch.setattr(installer, "run_logged_command", fake_run)
    (paths.vieneu_env_dir() / paths.PKG_MARKER_NAME).unlink()   # python.exe còn nhưng venv xoá dở
    asyncio.run(installer.install_vieneu(get_model("vieneu-v3-nano")))
    assert calls[0][1] == "venv" and calls[1][1:3] == ["pip", "install"]   # dựng lại, không pip vào venv hỏng
    pip = calls[1]
    assert pip[pip.index("--exclude-newer") + 1] == paths.VIENEU_EXCLUDE_NEWER and pip[-1] == paths.VIENEU_PACKAGE_SPEC
    warm = calls[2]
    assert warm[warm.index("--voices-file") + 1] == str(paths.voices_cache_file("nano"))


# ---------------- H4/M4: môi trường con + ghim revision ----------------
def test_subprocess_env_strips_insecure_keeps_mirror_and_offline_flag(env_home, monkeypatch):
    monkeypatch.setenv("UV_INSECURE_HOST", "evil.example")
    monkeypatch.setenv("UV_EXTRA_INDEX_URL", "https://evil.example/simple")
    monkeypatch.setenv("UV_INDEX_URL", "https://mirror.corp/simple")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")   # của người dùng: không được làm hỏng bước tải model
    env = paths.vieneu_subprocess_env()
    assert "UV_INSECURE_HOST" not in env and "UV_EXTRA_INDEX_URL" not in env
    assert env["UV_INDEX_URL"] == "https://mirror.corp/simple" and "HF_HUB_OFFLINE" not in env
    offline = paths.vieneu_subprocess_env({"X": "1"}, offline=True)
    assert offline["HF_HUB_OFFLINE"] == "1" and offline["X"] == "1" and "UV_INSECURE_HOST" not in offline


def test_revision_pins_are_full_shas_and_injected_only_when_missing():
    assert all(len(sha) == 40 and int(sha, 16) >= 0 for sha in pins.PINS.values()) and len(pins.PINS) == 3
    turbo = "pnnbao-ump/VieNeu-TTS-v3-Turbo"
    assert pins.pinned_kwargs((turbo, "a.onnx"), {})["revision"] == pins.PINS[turbo]
    assert pins.pinned_kwargs((), {"repo_id": turbo, "filename": "a"})["revision"] == pins.PINS[turbo]
    assert pins.pinned_kwargs((turbo, "a"), {"revision": "main"})["revision"] == "main"   # caller nêu rõ thì giữ
    assert "revision" not in pins.pinned_kwargs(("other/repo", "a"), {})


def test_apply_revision_pins_wraps_hf_hub_download_idempotently(monkeypatch):
    import types
    seen = []
    hub = types.ModuleType("huggingface_hub")
    fd = types.ModuleType("huggingface_hub.file_download")
    hub.hf_hub_download = lambda *a, **k: seen.append((a, k))
    hub.file_download = fd
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setitem(sys.modules, "huggingface_hub.file_download", fd)
    pins.apply_revision_pins()
    pins.apply_revision_pins()   # gọi lại không bọc chồng
    hub.hf_hub_download("pnnbao-ump/VieNeu-TTS-v3-Nano", "f.onnx", repo_type="model")
    fd.hf_hub_download("OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX", "c.onnx")
    assert len(seen) == 2 and seen[0][1]["revision"] == pins.PINS["pnnbao-ump/VieNeu-TTS-v3-Nano"]
    assert seen[1][1]["revision"] == pins.PINS["OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX"]


def test_warmup_dumps_voices_file_and_server_requires_token_env(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sidecar, "load_tts", lambda mode, precision: FakeVieneu())
    out = tmp_path / "voices.json"
    assert sidecar.main(["--mode", "nano", "--warmup", "--voices-file", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == {
        "default": "Adam", "voices": [{"id": "Adam", "name": "Adam"}, {"id": "Mai Anh", "name": "Mai Anh"}]}
    monkeypatch.delenv(sidecar.TOKEN_ENV, raising=False)
    with pytest.raises(SystemExit):
        sidecar.main(["--mode", "nano"])


# ---------------- M3: cache giọng tĩnh ----------------
def test_list_voices_reads_cache_without_touching_sidecar(env_home):
    cache = paths.voices_cache_file("nano")
    cache.write_text(json.dumps({"default": "Adam", "voices": [{"id": "Adam", "name": "Adam"}, {"id": "B"}]}),
                     encoding="utf-8")

    class Boom:
        def running_model_id(self):
            raise AssertionError("không được đụng sidecar")

        def ensure_running(self, *_a, **_k):
            raise AssertionError("không được khởi động sidecar")

    voices = asyncio.run(list_vieneu_voices("vieneu-v3-nano", manager=Boom()))
    assert [(v.id, v.name, v.is_default) for v in voices] == [("Adam", "Adam", True), ("B", "B", False)]


def test_list_voices_without_cache_does_not_evict_other_running_model(env_home):
    class Other:
        def running_model_id(self):
            return "vieneu-v3-turbo"

        def ensure_running(self, *_a, **_k):
            raise AssertionError("không được đá sidecar đang chạy")

    with pytest.raises(RuntimeError, match="tải lại"):
        asyncio.run(list_vieneu_voices("vieneu-v3-nano", manager=Other()))


# ---------------- M5: picker bỏ kết quả của model cũ ----------------
def test_picker_discards_stale_load_when_model_changes(env_home, monkeypatch):
    get_qapp()
    for mid in ("vieneu-v3-turbo", "vieneu-v3-nano"):
        d = store.model_dir(get_model(mid))
        d.mkdir(parents=True, exist_ok=True)
        (d / VIENEU_MARKER_FILE).write_text("{}")
    monkeypatch.setattr(picker_mod, "spawn_background_task", lambda coro, name: coro.close())
    monkeypatch.setattr(settings, "vieneu_voices", {})
    from src.core.vieneu_voice_list_cache import VieneuVoice
    gate = {}

    async def provider(model_id):
        await gate["event"].wait()
        return [VieneuVoice(f"voice-of-{model_id}", model_id, True)]

    async def scenario():
        gate["event"] = asyncio.Event()
        parent = QWidget()
        widget = VieneuVoicePickerWidget(provider=provider, parent=parent)
        widget.set_model("vieneu-v3-turbo")
        task = asyncio.ensure_future(widget.load())   # lượt nạp model A đang chờ
        await asyncio.sleep(0)
        widget.set_model("vieneu-v3-nano")   # đổi sang B khi widget còn ẩn
        gate["event"].set()
        await task
        return widget, parent

    widget, _parent = asyncio.run(scenario())
    assert widget._loaded_model_id == "" and widget.combo.currentData() != "voice-of-vieneu-v3-turbo"
    widget.commit()
    assert "vieneu-v3-nano" not in settings.vieneu_voices   # chưa nạp B → không ghi nhầm
    flush_qt_garbage()


# ---------------- L5: kill cả cây tiến trình ----------------
@pytest.mark.skipif(os.name != "nt", reason="taskkill /T chỉ có trên Windows")
def test_kill_process_tree_kills_grandchildren(tmp_path):
    child_code = "import time; time.sleep(60)"
    parent_code = (f"import subprocess,sys,time; c=subprocess.Popen([sys.executable,'-c',{child_code!r}]); "
                   "print(c.pid, flush=True); time.sleep(60)")
    proc = subprocess.Popen([sys.executable, "-c", parent_code], stdout=subprocess.PIPE)
    grandchild = int(proc.stdout.readline().decode().strip())
    assert sidecar.is_process_alive(grandchild)
    kill_process_tree(proc)
    deadline = time.monotonic() + 5
    while sidecar.is_process_alive(grandchild) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not sidecar.is_process_alive(grandchild)


def test_spec_bundles_only_sidecar_py_files():
    spec_text = (Path(__file__).resolve().parent.parent / "TedCompanion.spec").read_text(encoding="utf-8")
    assert 'vieneu_sidecar").glob("*.py")' in spec_text   # không kéo __pycache__ vào bản đóng gói
