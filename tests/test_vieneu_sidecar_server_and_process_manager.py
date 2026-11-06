"""VieNeu sidecar: server HTTP (model giả, ephemeral port). Process manager: test_vieneu_manager_and_engine_hardening.py."""

import asyncio
import importlib.util
import io
import json
import os
import threading
import urllib.error
import urllib.request
import wave

import pytest

from src.config import settings
from src.core import vieneu_sidecar_process_manager as pm
from src.core.vieneu_runtime_paths import sidecar_script_path, venv_python
from src.core.vieneu_sidecar_tts_engine import list_vieneu_voices

spec = importlib.util.spec_from_file_location("vieneu_sidecar_under_test", sidecar_script_path())
sidecar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sidecar)


class FakeVieneu:
    sample_rate = 24000
    _default_voice = "Adam"

    def __init__(self):
        self.calls = []

    def list_preset_voices(self):
        return [("Adam — nam", "Adam"), ("Mai Anh — nữ", "Mai Anh")]

    def infer(self, text, **kwargs):
        self.calls.append((text, kwargs))
        if kwargs.get("voice") == "Lạ":
            raise ValueError("Voice 'Lạ' not found")
        if text == "boom":
            raise RuntimeError("onnx exploded")
        import numpy as np
        return np.zeros(2400, dtype=np.float32) if text != "silent" else np.array([], dtype=np.float32)


@pytest.fixture
def server():
    fake = FakeVieneu()
    srv = sidecar.build_server(sidecar.SpeechService(fake, "nano"), 0, "secret")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield fake, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _req(url, body=None, token="secret"):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type")
    except urllib.error.HTTPError as err:
        return err.code, err.read(), None


def test_health_open_voices_and_speech_wav(server):
    fake, base = server
    assert _req(f"{base}/health", token="")[0] == 200
    status, body, _ = _req(f"{base}/v1/voices")
    voices = json.loads(body)
    assert status == 200 and voices["default"] == "Adam" and voices["voices"][1] == {"id": "Mai Anh", "name": "Mai Anh — nữ"}
    status, body, ctype = _req(f"{base}/v1/audio/speech",
                               {"input": "xin chào", "voice": "Mai Anh", "speed": 1.3, "response_format": "mp3"})
    assert status == 200 and ctype == "audio/wav"
    with wave.open(io.BytesIO(body)) as wf:
        assert wf.getframerate() == 24000 and wf.getnchannels() == 1 and wf.getnframes() == 2400
    assert fake.calls[-1] == ("xin chào", {"voice": "Mai Anh", "speed": 1.3})


def test_auth_required_except_health(server):
    _fake, base = server
    for token in ("", "wrong"):
        assert _req(f"{base}/v1/voices", token=token)[0] == 401
        assert _req(f"{base}/v1/audio/speech", {"input": "a"}, token=token)[0] == 401


def test_bad_requests_and_inference_errors_keep_server_alive(server):
    _fake, base = server
    assert _req(f"{base}/v1/audio/speech", {"input": "  "})[0] == 400
    assert _req(f"{base}/v1/audio/speech", {"input": "x", "voice": "Lạ"})[0] == 200   # giọng lạ → rơi về mặc định, không 400
    assert _req(f"{base}/v1/audio/speech", {"input": "x", "speed": "abc"})[0] == 400
    assert _req(f"{base}/v1/audio/speech", {"input": "silent"})[0] == 400
    assert _req(f"{base}/v1/audio/speech", {"input": "boom"})[0] == 500
    assert _req(f"{base}/v1/nope")[0] == 404
    assert _req(f"{base}/v1/audio/speech", {"input": "ổn"})[0] == 200


def test_turbo_mode_does_not_pass_speed():
    fake = FakeVieneu()
    sidecar.SpeechService(fake, "turbo").synthesize("a", None, 1.5)
    assert fake.calls == [("a", {})]


def test_list_vieneu_voices_against_real_sidecar_server(server, monkeypatch, tmp_path):
    _fake, base = server
    monkeypatch.setattr(settings, "data_dir", tmp_path)   # không có cache giọng → hỏi sidecar (đường cài bản cũ)

    class RealEndpointManager:
        def running_model_id(self):
            return None

        def ensure_running(self, model_id, precision="fp32"):
            return pm.SidecarEndpoint(f"{base}/v1", "secret", model_id)

    voices = asyncio.run(list_vieneu_voices("vieneu-v3-nano", manager=RealEndpointManager()))
    assert [(v.id, v.is_default) for v in voices] == [("Adam", True), ("Mai Anh", False)]
