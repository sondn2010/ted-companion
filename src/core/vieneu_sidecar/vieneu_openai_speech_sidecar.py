"""Sidecar VieNeu-TTS cho Ted: máy chủ HTTP tối giản kiểu OpenAI (chỉ stdlib + `vieneu`).

Chạy bằng Python 3.12 trong venv riêng (KHÔNG chạy trong tiến trình Ted):
    VIENEU_SIDECAR_TOKEN=T python vieneu_openai_speech_sidecar.py --mode turbo|nano [--precision fp32|int8] [--port 0]
    python vieneu_openai_speech_sidecar.py --mode nano --warmup [--voices-file F]   # tải model (revision ghim) + đọc thử + dump giọng

Token chỉ nhận qua biến môi trường (argv hiện trong danh sách tiến trình). Cổng 0 = tự chọn; in `READY port=N` SAU khi
đã nạp model và bind xong → tiến trình cha đọc cổng thật từ stdout (không có cửa sổ tranh chấp cổng).

Endpoint (bind 127.0.0.1, yêu cầu `Authorization: Bearer <token>` trừ /health):
    GET  /health?nonce=X    -> {"status": "ok", "proof": HMAC-SHA256(token, X)}   (cha xác minh danh tính, không lộ token)
    GET  /v1/voices         -> {"default": id|null, "voices": [{"id", "name"}]}
    POST /v1/audio/speech   {input, voice?, speed?, response_format?} -> audio/wav (luôn WAV, bỏ qua response_format)
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import os
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # nạp module anh em khi chạy như script
from vieneu_hf_revision_pins import apply_revision_pins  # noqa: E402
from vieneu_parent_process_watchdog import is_process_alive, start_parent_watchdog  # noqa: E402,F401  (test dùng lại qua module này)

MAX_BODY_BYTES = 256 * 1024
MAX_INPUT_CHARS = 4000   # chỉ là chốt chặn; Ted tự cắt câu dài thành khúc ≤ ~350 ký tự trước khi gửi
TOKEN_ENV = "VIENEU_SIDECAR_TOKEN"
WARMUP_TEXT = "Xin chào, đây là giọng đọc thử."
MODE_TO_SDK = {"turbo": "v3turbo", "nano": "v3nano"}


def load_tts(mode: str, precision: str):
    """Nạp model VieNeu (lần đầu sẽ tải file từ Hugging Face vào HF_HOME)."""
    apply_revision_pins()   # TRƯỚC import vieneu: mọi lượt tải HF dùng đúng commit đã ghim
    from vieneu import Vieneu   # import muộn: test thay bằng đối tượng giả, không cần cài vieneu
    kwargs = {"precision": precision} if mode == "turbo" else {}   # Nano chỉ có 1 bản ONNX
    return Vieneu(mode=MODE_TO_SDK[mode], **kwargs)


def to_wav_bytes(audio, sample_rate: int) -> bytes:
    """Mảng float32 [-1, 1] (numpy) -> WAV PCM16 mono."""
    import numpy as np
    pcm = (np.clip(np.asarray(audio, dtype=np.float32).reshape(-1), -1.0, 1.0) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


class SpeechService:
    """Bọc model: tuần tự hoá suy luận bằng lock (model không an toàn đa luồng)."""

    def __init__(self, tts, mode: str):
        self.tts, self.mode = tts, mode
        self._lock = threading.Lock()
        self._known_voices: set[str] | None = None

    def _voice_ids(self) -> set[str]:
        if self._known_voices is None:
            self._known_voices = {v["id"] for v in self.voices()["voices"]}
        return self._known_voices

    def voices(self) -> dict:
        items = [{"id": str(vid), "name": str(label)} for label, vid in self.tts.list_preset_voices()]
        default = getattr(self.tts, "_default_voice", None)
        return {"default": default or (items[0]["id"] if items else None), "voices": items}

    def synthesize(self, text: str, voice: str | None, speed: float | None) -> bytes:
        kwargs = {}
        if voice and voice not in self._voice_ids():
            print(f"WARN giọng {voice!r} không có trong model {self.mode} → dùng giọng mặc định", file=sys.stderr, flush=True)
            voice = None   # giọng lưu cho model khác / đã bị bỏ: đọc bằng giọng mặc định thay vì lỗi 400
        if voice:
            kwargs["voice"] = voice
        if self.mode == "nano" and speed:   # chỉ Nano hỗ trợ speed
            kwargs["speed"] = max(0.5, min(2.0, float(speed)))
        with self._lock:
            audio = self.tts.infer(text, **kwargs)
        if len(audio) == 0:
            raise ValueError("Model không tạo được âm thanh cho văn bản này.")
        return to_wav_bytes(audio, self.tts.sample_rate)


def make_handler(service: SpeechService, token: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):   # im lặng: tránh tràn log của tiến trình con
            pass

        timeout = 30   # socket timeout: chặn client cục bộ treo kết nối (slowloris)

        def _send(self, code: int, body: bytes, content_type: str = "application/json") -> None:
            if code >= 400:
                self.close_connection = True   # lỗi sớm có thể chưa đọc hết body → không giữ keep-alive (tránh lệch khung)
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

        def _authorized(self) -> bool:
            sent = self.headers.get("Authorization", "")
            if not token or not hmac.compare_digest(sent.encode("utf-8"), f"Bearer {token}".encode("utf-8")):
                self._json(401, {"error": "unauthorized"})
                return False
            return True

        def do_GET(self):
            if self.path == "/health" or self.path.startswith("/health?"):
                nonce = parse_qs(urlsplit(self.path).query).get("nonce", [""])[0]
                proof = hmac.new(token.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256).hexdigest() if nonce else ""
                return self._json(200, {"status": "ok", "mode": service.mode, "proof": proof})
            if not self._authorized():
                return
            if self.path == "/v1/voices":
                return self._json(200, service.voices())
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._authorized():
                return
            if self.path != "/v1/audio/speech":
                return self._json(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > MAX_BODY_BYTES:
                    return self._json(413 if length > MAX_BODY_BYTES else 400, {"error": "invalid body size"})
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                text = str(payload.get("input") or "").strip()
                if not text or len(text) > MAX_INPUT_CHARS:
                    return self._json(400, {"error": "input is empty or too long"})
                voice = payload.get("voice")
                speed = payload.get("speed")
                wav = service.synthesize(text, str(voice) if voice else None, float(speed) if speed else None)
            except (ValueError, KeyError, UnicodeDecodeError, TypeError) as exc:   # JSON hỏng, voice lạ, ...
                return self._json(400, {"error": str(exc)})
            except Exception as exc:   # lỗi suy luận: báo 500 nhưng giữ server sống
                return self._json(500, {"error": f"inference failed: {exc}"})
            self._send(200, wav, "audio/wav")

    return Handler


def build_server(service: SpeechService, port: int, token: str) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(service, token))
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=sorted(MODE_TO_SDK), required=True)
    parser.add_argument("--precision", choices=("fp32", "int8"), default="fp32")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--warmup", action="store_true")
    parser.add_argument("--voices-file", default="", help="warmup: ghi danh sách giọng (JSON) vào file này")
    parser.add_argument("--parent-pid", type=int, default=0, help="PID tiến trình Ted; mất → sidecar tự thoát")
    args = parser.parse_args(argv)
    token = os.environ.get(TOKEN_ENV, "")
    if not args.warmup and not token:
        parser.error(f"thiếu biến môi trường {TOKEN_ENV}")
    if args.parent_pid > 0 and not args.warmup:
        start_parent_watchdog(args.parent_pid)

    service = SpeechService(load_tts(args.mode, args.precision), args.mode)
    if args.warmup:
        wav = service.synthesize(WARMUP_TEXT, None, None)
        if args.voices_file:
            with open(args.voices_file, "w", encoding="utf-8") as fh:
                json.dump(service.voices(), fh, ensure_ascii=False)
        print(f"WARMUP_OK mode={args.mode} bytes={len(wav)}", flush=True)
        return 0
    server = build_server(service, args.port, token)
    print(f"READY port={server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
