"""Quản lý tiến trình sidecar VieNeu: khởi động lười, chờ `READY port=N`, xác minh /health, tái dùng, tự dựng lại khi chết/treo.

- Sidecar tự bind cổng 0 rồi in cổng thật ra stdout (không còn chọn trước cổng → không có cửa sổ tranh chấp).
- Token ngẫu nhiên truyền qua biến môi trường (argv hiện trong danh sách tiến trình). /health xác minh danh tính bằng
  HMAC của nonce → token không bao giờ gửi tới tiến trình lạ; mọi gọi 127.0.0.1 bỏ qua proxy hệ thống.
- stop() KHÔNG chờ khóa khởi động: tăng epoch + kill ngay → ensure_running đang chờ sẽ bỏ cuộc (UI thread không bị treo).
- disable()/enable(): chặn khởi động lại trong lúc gỡ cài đặt.
ensure_running() là đồng bộ (gọi qua asyncio.to_thread); stop() nối vào QApplication.aboutToQuit (src/main.py) + atexit.
"""

import atexit
from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
import os
import secrets
import subprocess
import threading
import time
import urllib.request
from typing import Callable, Optional

from src.core.tts_service import no_console_window_flags
from src.core.vieneu_runtime_paths import (
    SIDECAR_MODE_BY_MODEL_ID, log_dir, sidecar_script_path, venv_is_usable, venv_python, vieneu_subprocess_env,
)

logger = logging.getLogger("ted")

STARTUP_TIMEOUT_S = 90.0   # nạp model ONNX từ cache (offline) vài giây → vài chục giây trên máy yếu
TOKEN_ENV = "VIENEU_SIDECAR_TOKEN"
_LOOPBACK_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # bỏ qua HTTP(S)_PROXY và proxy registry Windows


@dataclass(frozen=True)
class SidecarEndpoint:
    base_url: str    # http://127.0.0.1:<port>/v1 — truyền thẳng cho RemoteOpenAITTSEngine
    token: str
    model_id: str


def _probe_health(port: int, token: str) -> bool:
    """Đúng sidecar của ta ⇔ /health trả proof = HMAC-SHA256(token, nonce). Không gửi token đi đâu cả."""
    nonce = secrets.token_hex(8)
    try:
        with _LOOPBACK_OPENER.open(f"http://127.0.0.1:{port}/health?nonce={nonce}", timeout=2) as resp:
            proof = json.loads(resp.read(4096).decode("utf-8")).get("proof", "")
    except (OSError, ValueError, AttributeError):
        return False
    expected = hmac.new(token.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(str(proof), expected)


class _StartupAborted(RuntimeError):
    pass


class VieneuSidecarManager:
    def __init__(self, popen: Callable = subprocess.Popen, probe: Callable[[int, str], bool] = _probe_health,
                 startup_timeout: float = STARTUP_TIMEOUT_S):
        self._popen, self._probe = popen, probe
        self._startup_timeout = startup_timeout
        self._start_lock = threading.RLock()   # tuần tự hoá khởi động (có thể giữ tới 90s)
        self._state_lock = threading.Lock()    # chỉ bảo vệ _proc/_endpoint/_epoch: giữ cực ngắn
        self._proc = None
        self._endpoint: Optional[SidecarEndpoint] = None
        self._epoch = 0
        self._disabled = 0

    def is_running(self) -> bool:
        with self._state_lock:
            return self._proc is not None and self._proc.poll() is None

    def running_model_id(self) -> Optional[str]:
        with self._state_lock:
            alive = self._proc is not None and self._proc.poll() is None
            return self._endpoint.model_id if alive and self._endpoint else None

    def disable(self) -> None:
        """Chặn ensure_running (đang gỡ cài đặt). Gọi lồng nhau được; mỗi disable() cần 1 enable()."""
        with self._state_lock:
            self._disabled += 1

    def enable(self) -> None:
        with self._state_lock:
            self._disabled = max(0, self._disabled - 1)

    def ensure_running(self, model_id: str, precision: str = "fp32") -> SidecarEndpoint:
        """Trả về endpoint đang sống cho model_id; khởi động (hoặc dựng lại khi chết / đổi model) nếu cần."""
        mode = SIDECAR_MODE_BY_MODEL_ID.get(model_id)
        if mode is None:
            raise ValueError(f"{model_id} không phải model VieNeu.")
        with self._start_lock:
            self._raise_if_disabled()
            if self.running_model_id() == model_id:
                return self._endpoint
            self._kill()
            if not venv_is_usable():
                raise RuntimeError("Chưa cài VieNeu-TTS — vào Cài đặt → Giọng nói để tải.")
            with self._state_lock:
                epoch = self._epoch
            token = secrets.token_urlsafe(24)
            log_dir().mkdir(parents=True, exist_ok=True)
            log_path = log_dir() / "vieneu_sidecar.log"
            env = vieneu_subprocess_env({TOKEN_ENV: token}, offline=True)   # sau khi cài: không gọi Hugging Face
            proc = self._popen(
                [str(venv_python()), str(sidecar_script_path()), "--mode", mode, "--precision", precision,
                 "--port", "0", "--parent-pid", str(os.getpid())],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=no_console_window_flags(),
            )
            with self._state_lock:
                aborted = epoch != self._epoch or bool(self._disabled)   # stop()/gỡ cài đặt xen vào giữa
                if not aborted:
                    self._proc = proc
            if aborted:
                self._terminate(proc)
                raise _StartupAborted("Đã dừng khởi động sidecar VieNeu.")
            try:
                port = self._wait_ready(proc, token, epoch, log_path)
            except BaseException:
                self._kill()
                raise
            self._endpoint = SidecarEndpoint(f"http://127.0.0.1:{port}/v1", token, model_id)
            logger.info("Sidecar VieNeu (%s) chạy ở cổng %d", mode, port)
            return self._endpoint

    def _raise_if_disabled(self) -> None:
        if self._disabled:
            raise RuntimeError("Đang gỡ cài đặt VieNeu-TTS — chưa thể đọc.")

    def _wait_ready(self, proc, token: str, epoch: int, log_path) -> int:
        """Đọc stdout (ghi tee vào log) tới dòng `READY port=N`, rồi xác minh /health."""
        ready: dict = {}
        got_ready = threading.Event()

        def pump() -> None:
            with log_path.open("ab") as log:
                for raw in iter(proc.stdout.readline, b""):   # tiếp tục rút cạn sau READY để pipe không đầy
                    log.write(raw)
                    log.flush()
                    line = raw.decode("utf-8", "replace").strip()
                    if line.startswith("READY port=") and "port" not in ready:
                        ready["port"] = int(line.split("=", 1)[1])
                        got_ready.set()

        threading.Thread(target=pump, name="vieneu-sidecar-stdout", daemon=True).start()
        deadline = time.monotonic() + self._startup_timeout
        while time.monotonic() < deadline:
            if self._epoch != epoch:
                raise _StartupAborted("Đã dừng khởi động sidecar VieNeu.")
            if got_ready.wait(0.25):
                if self._probe(ready["port"], token):
                    return ready["port"]
                time.sleep(0.25)
            if self._epoch != epoch:   # stop() có thể vừa kill tiến trình: ưu tiên báo "đã dừng" thay vì "thoát sớm"
                raise _StartupAborted("Đã dừng khởi động sidecar VieNeu.")
            if proc.poll() is not None:
                time.sleep(0.2)   # chờ luồng pump ghi nốt đuôi log
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-400:]
                raise RuntimeError(f"Sidecar VieNeu thoát sớm. Log: {log_path}\n{tail}")
        raise RuntimeError(f"Sidecar VieNeu không phản hồi sau {self._startup_timeout:.0f}s. Log: {log_path}")

    @staticmethod
    def _terminate(proc) -> None:
        if proc is None or proc.poll() is not None:
            return
        proc.kill()   # sidecar chỉ giữ model trong RAM: không cần dọn dẹp lịch sự, kill ngay cho nhanh
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            logger.warning("Sidecar VieNeu chưa thoát sau kill 3s")

    def _kill(self) -> None:
        with self._state_lock:
            proc, self._proc, self._endpoint = self._proc, None, None
        self._terminate(proc)

    def stop(self) -> None:
        """Dừng ngay, không chờ khóa khởi động: tăng epoch để ensure_running đang chờ tự bỏ cuộc."""
        with self._state_lock:
            self._epoch += 1
        self._kill()

    def mark_unhealthy(self, endpoint: SidecarEndpoint) -> None:
        """Yêu cầu tới sidecar bị timeout/đứt: kill để lần dùng sau dựng lại (chỉ khi còn là sidecar đó)."""
        with self._state_lock:
            current = self._endpoint is endpoint
        if current:
            logger.warning("Sidecar VieNeu không phản hồi → dựng lại ở lần đọc kế tiếp")
            self._kill()


vieneu_sidecar_manager = VieneuSidecarManager()
atexit.register(vieneu_sidecar_manager.stop)   # dự phòng khi thoát không qua aboutToQuit
