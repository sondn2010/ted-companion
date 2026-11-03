"""
Dịch vụ Nhận diện giọng nói thành văn bản (Speech-to-Text - STT) đa chế độ.

Kiến trúc tách bạch (Decoupled Engine Provider Pattern):
1. BaseSTTEngine (Giao diện trừu tượng):
   - Chuẩn hoá phương thức `transcribe(audio_data, language) -> str`.
   - Giúp lập trình viên dễ dàng cắm thêm các engine mới (Whisper, Faster-Whisper,
     Sherpa-onnx, Vosk, Whisper.cpp, v.v.) mà không cần can thiệp vào tầng ghi âm hay UI.
2. RemoteOpenAISTTEngine:
   - Kết nối máy chủ STT qua mạng tuân theo chuẩn OpenAI API (`/v1/audio/transcriptions`).
   - Tương thích Faster-Whisper Server, Whisper.cpp Server, Speaches, OpenAI Whisper API.
3. LocalEmbeddedSTTEngine:
   - Chạy model whisper.cpp OFFLINE người dùng tự tải trong Cài đặt (~/.ted/voice_models, không nằm trong bộ cài).
   - Gọi binary `whisper-cli` (Windows tải kèm, macOS cài qua brew) — không cần kết nối mạng.
4. STTService (Facade Layer):
   - Quản lý quá trình thu âm từ micro.
   - Quản lý vòng đời tệp âm thanh tạm thời.
   - Tự động chuyển đổi engine theo cấu hình (Auto / Embedded / Server).
"""

from abc import ABC, abstractmethod
import asyncio
from datetime import datetime
import io
import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Optional, Tuple

import httpx
from PySide6.QtCore import QObject, Signal

from src.config import settings
from src.core.offline_voice_model_store import find_runtime_executable, installed_models, model_main_path, resolve_model
from src.core.tts_service import no_console_window_flags

logger = logging.getLogger("ted")

# Dòng log của whisper-cli lọt vào stdout (vd. "[00:00.000 --> ...]") — bỏ khi ghép văn bản
_WHISPER_NOISE_RE = re.compile(r"^\s*(\[[^\]]*\]\s*)+")


def is_embedded_stt_available() -> bool:
    """True khi đã tải ít nhất 1 model whisper.cpp VÀ có bộ chạy `whisper-cli` (tải kèm hoặc trong PATH)."""
    return bool(installed_models("stt")) and find_runtime_executable("stt") is not None


# =====================================================================
# TẦNG 1: CÁC NHÀ CUNG CẤP ĐỘNG CƠ STT (ENGINE PROVIDERS)
# =====================================================================

class BaseSTTEngine(ABC):
    """Giao diện trừu tượng cho tất cả các bộ nhận diện giọng nói STT."""

    @abstractmethod
    async def transcribe(
        self,
        audio_data: bytes,
        filename: str = "audio.wav",
        language: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> str:
        """Chuyển đổi âm thanh (bytes) thành văn bản (text)."""
        pass


class RemoteOpenAISTTEngine(BaseSTTEngine):
    """
    Engine STT qua mạng tương thích chuẩn OpenAI API (/v1/audio/transcriptions).
    Phù hợp cho bản cài đặt Lite hoặc khi người dùng trỏ vào VPS / local server.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.server_url = (server_url or getattr(settings, "stt_server_url", "http://127.0.0.1:8881/v1")).rstrip("/")
        self.api_key = api_key if api_key is not None else getattr(settings, "stt_api_key", "")
        self.model = model or getattr(settings, "stt_model", "whisper-1")

    async def transcribe(
        self,
        audio_data: bytes,
        filename: str = "audio.wav",
        language: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> str:
        endpoint = (
            self.server_url
            if self.server_url.endswith("/audio/transcriptions")
            else f"{self.server_url}/audio/transcriptions"
        )
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = {
            "model": self.model,
            "response_format": "json",
        }
        if language:
            data["language"] = language

        files = {
            "file": (filename, audio_data, "audio/wav"),
        }

        if http_client is not None:
            resp = await http_client.post(endpoint, data=data, files=files, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"Server STT trả về lỗi {resp.status_code}: {resp.text[:150]}")
            result = resp.json()
            return result.get("text", "").strip()

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(endpoint, data=data, files=files, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"Server STT trả về lỗi {resp.status_code}: {resp.text[:150]}")
            result = resp.json()
            return result.get("text", "").strip()


class LocalEmbeddedSTTEngine(BaseSTTEngine):
    """
    Engine STT offline: model whisper.cpp đã tải (~/.ted/voice_models/stt) + binary `whisper-cli`.
    Âm thanh vào là WAV (whisper-cli tự resample về 16kHz).
    """

    def __init__(self, model_id: Optional[str] = None):
        self.model_id = model_id if model_id is not None else getattr(settings, "stt_local_model", "")

    async def transcribe(
        self,
        audio_data: bytes,
        filename: str = "audio.wav",
        language: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> str:
        exe = find_runtime_executable("stt")
        if exe is None:
            raise RuntimeError("Chưa có bộ chạy nhận diện giọng nói offline — vào Cài đặt → Tải mô hình nhận giọng nói.")
        model = resolve_model("stt", self.model_id)
        if model is None:
            raise RuntimeError("Chưa tải mô hình nhận giọng nói offline — vào Cài đặt → Tải mô hình nhận giọng nói.")
        lang = language or getattr(settings, "stt_language", "") or "auto"
        return await asyncio.to_thread(self._run_whisper, exe, model_main_path(model), audio_data, lang)

    @staticmethod
    def _run_whisper(exe: Path, model_path: Path, audio_data: bytes, language: str) -> str:
        fd, wav_name = tempfile.mkstemp(prefix="ted_stt_", suffix=".wav")
        with os.fdopen(fd, "wb") as fh:
            fh.write(audio_data)
        try:
            proc = subprocess.run(
                [str(exe), "-m", str(model_path), "-f", wav_name, "-l", language, "-nt", "-np"],
                capture_output=True, timeout=300, cwd=str(exe.parent), creationflags=no_console_window_flags(),
            )
            if proc.returncode != 0:
                err = proc.stderr.decode("utf-8", "replace")[-200:]
                raise RuntimeError(f"whisper-cli lỗi (mã {proc.returncode}): {err}")
            lines = [_WHISPER_NOISE_RE.sub("", ln).strip() for ln in proc.stdout.decode("utf-8", "replace").splitlines()]
            return " ".join(ln for ln in lines if ln).strip()
        finally:
            Path(wav_name).unlink(missing_ok=True)


# =====================================================================
# TẦNG 2: DỊCH VỤ ĐIỀU PHỐI (FACADE SERVICE LAYER)
# =====================================================================

class STTService(QObject):
    """Dịch vụ điều phối nhận diện giọng nói STT toàn ứng dụng."""

    recording_started = Signal()
    recording_stopped = Signal()
    transcription_ready = Signal(str)  # text kết quả
    transcription_error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.is_recording: bool = False
        self._current_audio_file: Optional[Path] = None

    def get_effective_mode(self) -> str:
        """Trả về 'embedded' hoặc 'server'."""
        mode = getattr(settings, "stt_mode", "auto")
        if mode == "auto":
            return "embedded" if is_embedded_stt_available() else "server"
        if mode == "embedded" and not is_embedded_stt_available():
            return "server"
        return mode

    def get_engine(
        self,
        server_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> BaseSTTEngine:
        """Factory tạo Engine tương ứng với chế độ hiện tại."""
        mode = self.get_effective_mode()
        if mode == "embedded":
            return LocalEmbeddedSTTEngine()
        return RemoteOpenAISTTEngine(server_url=server_url, api_key=api_key, model=model)

    async def transcribe_bytes(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        language: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> str:
        """Nhận diện văn bản từ chuỗi byte âm thanh."""
        if not audio_bytes:
            raise ValueError("Dữ liệu âm thanh rỗng.")

        engine = self.get_engine()
        return await engine.transcribe(
            audio_bytes, filename=filename, language=language, http_client=http_client
        )

    async def transcribe_file(
        self,
        file_path: Path,
        language: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> str:
        """Nhận diện văn bản từ tệp âm thanh trên đĩa."""
        if not file_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file âm thanh: {file_path}")

        audio_bytes = file_path.read_bytes()
        return await self.transcribe_bytes(
            audio_bytes, filename=file_path.name, language=language, http_client=http_client
        )

    async def test_connection(
        self,
        server_url: str,
        api_key: str = "",
        model: str = "whisper-1",
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> Tuple[bool, str]:
        """Kiểm tra kết nối tới máy chủ STT."""
        engine = RemoteOpenAISTTEngine(server_url=server_url, api_key=api_key, model=model)
        # Tạo 1 đoạn dummy WAV 44 byte header rỗng để ping server
        dummy_wav = (
            b"RIFF\x28\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
            b"\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x04\x00\x00\x00\x00\x00\x00\x00"
        )
        try:
            await engine.transcribe(dummy_wav, filename="test.wav", http_client=http_client)
            return True, "Kết nối máy chủ STT thành công!"
        except Exception as exc:
            return False, f"Lỗi STT: {exc}"

    async def test_offline_model(self, model_id: str) -> Tuple[bool, str]:
        """Chạy thử model offline với 1 giây im lặng (16kHz mono) để chắc chắn bộ chạy + model hoạt động."""
        silence = b"\x00\x00" * 16000
        header = (
            b"RIFF" + (36 + len(silence)).to_bytes(4, "little") + b"WAVEfmt "
            + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
            + (16000).to_bytes(4, "little") + (32000).to_bytes(4, "little") + (2).to_bytes(2, "little")
            + (16).to_bytes(2, "little") + b"data" + len(silence).to_bytes(4, "little")
        )
        try:
            await LocalEmbeddedSTTEngine(model_id).transcribe(header + silence, language="vi")
            return True, "Mô hình nhận giọng nói offline hoạt động tốt!"
        except Exception as exc:
            return False, f"Lỗi STT offline: {exc}"


# Singleton mặc định dùng cho app
stt_service = STTService()
