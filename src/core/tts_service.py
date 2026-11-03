"""
Dịch vụ Chuyển văn bản thành giọng nói (Text-to-Speech - TTS) đa chế độ.

Kiến trúc tách bạch (Decoupled Engine Provider Pattern):
1. BaseTTSEngine (Giao diện trừu tượng):
   - Chuẩn hoá phương thức `synthesize(text, voice, speed) -> bytes`.
   - Giúp lập trình viên dễ dàng cắm thêm các engine mới (Kokoro, Piper, Coqui, ElevenLabs, v.v.)
     mà không cần can thiệp vào tầng âm thanh (QMediaPlayer) hay giao diện người dùng (UI).
2. RemoteOpenAITTSEngine:
   - Kết nối máy chủ TTS qua mạng tuân theo chuẩn OpenAI API (`/v1/audio/speech`).
   - Tương thích Kokoro-FastAPI, Piper HTTP Server, Edge-TTS Server, OpenAI Audio API.
3. LocalEmbeddedTTSEngine:
   - Chạy giọng Piper OFFLINE người dùng tự tải trong Cài đặt (~/.ted/voice_models, không nằm trong bộ cài).
   - Gọi binary `piper` (tải kèm lần đầu) qua subprocess: 100% offline, không cần internet.
4. TTSService (Facade Layer):
   - Tự động nhận diện ngôn ngữ Tiếng Việt vs Tiếng Anh.
   - Làm sạch văn bản (loại bỏ thẻ [MOOD:...], <json>, markdown).
   - Quản lý thiết bị phát âm thanh Qt (QMediaPlayer, QAudioOutput).
   - Tự động chuyển đổi engine theo cấu hình (Auto / Embedded / Server).
"""

from abc import ABC, abstractmethod
import asyncio
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Callable, Optional, Tuple

import httpx
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from src.config import settings
from src.core.character_persona_profiles import active_voice_override
from src.core.offline_voice_model_catalog import get_model
from src.core.speech_text_punctuation_and_emoji_normalizer import normalize_text_for_speech
from src.core.tts_chunk_playback_queue import ChunkPlaybackQueue
from src.core.tts_gapless_pcm_stream_player import GaplessPcmStreamPlayer
from src.core.offline_voice_model_store import find_runtime_executable, installed_models, model_main_path, resolve_model

logger = logging.getLogger("ted")

# Ký tự có dấu đặc trưng của tiếng Việt để nhận diện ngôn ngữ câu thoại
VIETNAMESE_CHARS_RE = re.compile(
    r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)

# Thẻ [MOOD:...], [TED_...], <json>...</json> cần lọc sạch trước khi đọc giọng nói
TAGS_RE = re.compile(r"\[[A-Z_]+(?::[^\]]*)?\]|<json>.*?</json>", re.S)


def detect_language(text: str) -> str:
    """Phát hiện văn bản là Tiếng Việt ('vi') hay Tiếng Anh ('en')."""
    clean = TAGS_RE.sub("", text).strip()
    if VIETNAMESE_CHARS_RE.search(clean):
        return "vi"
    return "en"


def prepare_text_for_speech(text: str) -> str:
    """Bỏ thẻ điều khiển, ký hiệu markdown; SVG bị bỏ qua, LaTeX / bảng đổi sang chữ đọc được (x², √, …).
    GIỮ xuống dòng, ngoặc kép, gạch ngang, "..." để bộ tiền xử lý VieNeu nhấn nhá theo đoạn / hội thoại."""
    from src.ui.rich_content.latex_to_speakable_text import speakable_text_from_rich_reply
    clean = speakable_text_from_rich_reply(TAGS_RE.sub("", text))
    # Bỏ ký hiệu markdown (**, __, #, `, ~); gạch đầu dòng "-"/"•" do normalizer xử lý theo dòng
    return re.sub(r"[*_`#~]", "", clean)


def clean_text_for_speech(text: str) -> str:
    """Như prepare_text_for_speech, rồi bỏ emoji/icon; mỗi dòng thành một câu có dấu kết thúc và dấu câu được chuẩn hoá
    để giọng đọc ngắt nghỉ đúng (Piper / máy chủ)."""
    return normalize_text_for_speech(prepare_text_for_speech(text))


def is_embedded_tts_available() -> bool:
    """True khi đã tải 1 giọng VieNeu (sidecar tự chứa môi trường), hoặc ≥ 1 giọng Piper VÀ có bộ chạy `piper`."""
    models = installed_models("tts")
    if any(m.engine == "vieneu" for m in models):
        return True
    return bool(models) and find_runtime_executable("tts") is not None


def is_tts_configured() -> bool:
    """Đủ điều kiện để Ted nói: đã từng bật TTS, chọn chế độ máy chủ, hoặc đã tải giọng offline.
    Dùng để ẩn/hiện nút 🔊 bật/tắt nói trong bong bóng chat."""
    return bool(
        getattr(settings, "tts_configured", False) or getattr(settings, "tts_enabled", False)
        or getattr(settings, "tts_mode", "auto") == "server" or is_embedded_tts_available()
    )


def no_console_window_flags() -> int:
    """Không bật cửa sổ console đen khi gọi binary trên Windows."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


# =====================================================================
# TẦNG 1: CÁC NHÀ CUNG CẤP ĐỘNG CƠ TTS (ENGINE PROVIDERS)
# =====================================================================

class BaseTTSEngine(ABC):
    """Giao diện trừu tượng cho tất cả các bộ tổng hợp giọng nói."""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        http_client: Optional[httpx.AsyncClient] = None,
        should_continue: Optional[Callable[[], bool]] = None,   # chỉ engine đọc theo khúc (VieNeu) dùng; còn lại bỏ qua
        on_chunk: Optional[Callable[[bytes], None]] = None,     # VieNeu: giao từng khúc để phát sớm (trả b""); còn lại bỏ qua
    ) -> bytes:
        """Chuyển đổi text thành mảng byte âm thanh (mp3/wav)."""
        pass


class RemoteOpenAITTSEngine(BaseTTSEngine):
    """
    Engine TTS qua mạng tương thích chuẩn OpenAI API (/v1/audio/speech).
    Phù hợp cho bản cài đặt Lite hoặc khi người dùng trỏ vào VPS / local server.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.server_url = (server_url or getattr(settings, "tts_server_url", "http://127.0.0.1:8880/v1")).rstrip("/")
        self.api_key = api_key if api_key is not None else getattr(settings, "tts_api_key", "")
        self.model = model or getattr(settings, "tts_model", "tts-1")

    async def synthesize(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        http_client: Optional[httpx.AsyncClient] = None,
        should_continue: Optional[Callable[[], bool]] = None,   # chỉ engine đọc theo khúc (VieNeu) dùng; còn lại bỏ qua
        on_chunk: Optional[Callable[[bytes], None]] = None,     # VieNeu: giao từng khúc để phát sớm (trả b""); còn lại bỏ qua
    ) -> bytes:
        endpoint = self.server_url if self.server_url.endswith("/audio/speech") else f"{self.server_url}/audio/speech"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {"model": self.model, "input": text, "voice": voice, "speed": speed, "response_format": "mp3"}

        async def _post(client: httpx.AsyncClient) -> bytes:
            resp = await client.post(endpoint, json=payload, headers=headers)
            if resp.status_code == 400 and "response_format" in resp.text and payload["response_format"] != "wav":
                # Máy chủ chỉ hỗ trợ pcm/wav (vd. VieNeu-TTS Docker): thử lại với WAV
                payload["response_format"] = "wav"
                resp = await client.post(endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    return fix_streaming_wav_header(resp.content)
            if resp.status_code != 200:
                raise RuntimeError(f"Server TTS trả về mã lỗi HTTP {resp.status_code}: {resp.text[:150]}")
            return resp.content

        if http_client is not None:
            return await _post(http_client)
        async with httpx.AsyncClient(timeout=20.0) as client:
            return await _post(client)


def fix_streaming_wav_header(data: bytes) -> bytes:
    """WAV stream (độ dài placeholder 0xFFFFFFFF) → ghi lại kích thước thật để trình phát biết độ dài."""
    if len(data) < 44 or data[:4] != b"RIFF" or data[36:40] != b"data":
        return data
    import struct
    return data[:4] + struct.pack("<I", len(data) - 8) + data[8:40] + struct.pack("<I", len(data) - 44) + data[44:]


class LocalEmbeddedTTSEngine(BaseTTSEngine):
    """
    Engine TTS offline: giọng Piper đã tải về (~/.ted/voice_models/tts) + binary `piper`.
    `voice` là id giọng trong catalog; nếu trống/không hợp lệ thì tự chọn giọng đã tải đúng ngôn ngữ của câu.
    """

    async def synthesize(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        http_client: Optional[httpx.AsyncClient] = None,
        should_continue: Optional[Callable[[], bool]] = None,   # chỉ engine đọc theo khúc (VieNeu) dùng; còn lại bỏ qua
        on_chunk: Optional[Callable[[bytes], None]] = None,     # VieNeu: giao từng khúc để phát sớm (trả b""); còn lại bỏ qua
    ) -> bytes:
        model = resolve_model("tts", voice, detect_language(text)) or resolve_model("tts", voice)
        if model is None:
            raise RuntimeError("Chưa tải giọng đọc offline nào — vào Cài đặt → Tải giọng đọc offline.")
        if model.engine == "vieneu":   # VieNeu chạy bằng sidecar Python riêng, không dùng binary piper
            from src.core.vieneu_sidecar_tts_engine import VieneuSidecarTTSEngine
            return await VieneuSidecarTTSEngine(model.id).synthesize(
                text, voice, speed, http_client=http_client, should_continue=should_continue, on_chunk=on_chunk)
        text = normalize_text_for_speech(text)   # Piper: văn bản phẳng, dấu câu đã chuẩn hoá
        exe = find_runtime_executable("tts")
        if exe is None:
            raise RuntimeError("Chưa có bộ chạy giọng nói offline — vào Cài đặt → Tải giọng đọc offline.")
        length_scale = 1.0 / max(0.5, min(2.0, speed or 1.0))   # Piper: length_scale nhỏ = đọc nhanh
        return await asyncio.to_thread(self._run_piper, exe, model_main_path(model), text, length_scale)

    @staticmethod
    def _run_piper(exe: Path, model_path: Path, text: str, length_scale: float) -> bytes:
        fd, out_name = tempfile.mkstemp(prefix="ted_tts_", suffix=".wav")
        os.close(fd)
        out = Path(out_name)
        try:
            proc = subprocess.run(
                [str(exe), "--model", str(model_path), "--output_file", str(out), "--length_scale", f"{length_scale:.2f}"],
                input=text.encode("utf-8"), capture_output=True, timeout=120,
                cwd=str(exe.parent), creationflags=no_console_window_flags(),
            )
            if proc.returncode != 0 or out.stat().st_size == 0:
                err = proc.stderr.decode("utf-8", "replace")[-200:]
                raise RuntimeError(f"Piper lỗi (mã {proc.returncode}): {err}")
            return out.read_bytes()
        finally:
            out.unlink(missing_ok=True)


# =====================================================================
# TẦNG 2: DỊCH VỤ ĐIỀU PHỐI (FACADE SERVICE LAYER)
# =====================================================================

class TTSService(QObject):
    """Dịch vụ điều phối âm thanh TTS toàn ứng dụng."""

    playback_started = Signal(str)  # text
    playback_finished = Signal()
    playback_error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.9)
        self.player.setAudioOutput(self.audio_output)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(lambda *_: self._on_media_status_changed(QMediaPlayer.MediaStatus.InvalidMedia))
        # Gọi qua lambda để lớp con (test) ghi đè _play_bytes / _player_busy vẫn có tác dụng
        self._chunk_queue = ChunkPlaybackQueue(play=lambda data: self._play_bytes(data), is_busy=lambda: self._player_busy())
        # Khúc WAV PCM (VieNeu/Piper) nối liền vào 1 luồng âm thanh → không ngắt ở dấu câu; MP3 vẫn qua QMediaPlayer
        self._pcm_stream = GaplessPcmStreamPlayer(volume=0.9, parent=self)
        self._pcm_stream.finished.connect(self._on_pcm_stream_finished)
        self._delivered_generation = -1  # lượt đã nhận khúc gần nhất: khúc đầu của lượt mới thì cắt âm thanh cũ

        self._current_temp_file: Optional[Path] = None
        self._lock = asyncio.Lock()
        self._generation = 0  # tăng mỗi lần speak()/stop(): chỉ câu mới nhất được phát
        self._last_stopped_generation = -1  # lượt bị stop() gần nhất (câu đang tổng hợp dở đã bị huỷ)
        self._synthesizing = 0  # số câu đang tổng hợp dở
        self._awaiting_playback = False  # đã gọi play() nhưng loa chưa báo PlayingState

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._awaiting_playback = False   # loa đã thật sự phát; từ giờ PlayingState đại diện cho "bận"
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.playback_finished.emit()

    def get_effective_mode(self) -> str:
        """Trả về 'embedded' hoặc 'server'."""
        mode = getattr(settings, "tts_mode", "auto")
        if mode == "auto":
            return "embedded" if is_embedded_tts_available() else "server"
        if mode == "embedded" and not is_embedded_tts_available():
            return "server"
        return mode

    def get_engine(
        self,
        server_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> BaseTTSEngine:
        """Factory tạo Engine tương ứng với chế độ hiện tại."""
        mode = self.get_effective_mode()
        if mode == "embedded":
            return LocalEmbeddedTTSEngine()
        return RemoteOpenAITTSEngine(server_url=server_url, api_key=api_key, model=model)

    def pick_voice(self, lang: str) -> str:
        persona = active_voice_override()   # nhân vật đang hiện có giọng riêng (click 5 lần lên pet để cấu hình)
        if self.get_effective_mode() == "embedded":   # giọng offline: id model đã tải ("" = tự chọn theo ngôn ngữ)
            own = (persona.local_voice_vi if lang == "vi" else persona.local_voice_en) if persona else ""
            return own or getattr(settings, "tts_local_voice_vi" if lang == "vi" else "tts_local_voice_en", "")
        own = (persona.voice_vi if lang == "vi" else persona.voice_en) if persona else ""
        if own:
            return own
        if lang == "vi":
            return getattr(settings, "tts_voice_vi", "vi-VN-Standard-A")
        return getattr(settings, "tts_voice_en", "en-US-Standard-C")

    async def synthesize(
        self,
        text: str,
        lang: Optional[str] = None,
        voice: Optional[str] = None,
        server_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        should_continue: Optional[Callable[[], bool]] = None,
        on_chunk: Optional[Callable[[bytes], None]] = None,
    ) -> bytes:
        """
        Tổng hợp giọng nói từ văn bản.
        Tự động chọn Engine (Local Embedded hoặc Remote Server) theo cấu hình và bộ cài.
        """
        prepared = prepare_text_for_speech(text)
        clean = normalize_text_for_speech(prepared)
        if not clean:
            raise ValueError("Văn bản rỗng sau khi lọc.")

        target_lang = lang or detect_language(clean)
        target_voice = voice or self.pick_voice(target_lang)
        persona = active_voice_override()
        target_speed = speed if speed is not None else (persona.speed if persona else getattr(settings, "tts_speed", 1.0))

        # Sử dụng Engine Provider đã tách rời
        if server_url or api_key or model:
            engine = RemoteOpenAITTSEngine(server_url=server_url, api_key=api_key, model=model)
        else:
            engine = self.get_engine()

        # Engine offline nhận văn bản còn cấu trúc dòng (VieNeu cần để ngắt nghỉ theo đoạn; Piper tự làm phẳng)
        engine_text = prepared if isinstance(engine, LocalEmbeddedTTSEngine) else clean
        return await engine.synthesize(engine_text, target_voice, target_speed, http_client=http_client,
                                       should_continue=should_continue, on_chunk=on_chunk)

    # Giữ tương thích ngược cho các phương thức cũ
    async def _synthesize_embedded(self, text: str, lang: str, voice: str) -> bytes:
        engine = LocalEmbeddedTTSEngine()
        return await engine.synthesize(text, voice)

    async def _synthesize_remote(
        self,
        text: str,
        voice: str,
        server_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> bytes:
        engine = RemoteOpenAITTSEngine(server_url=server_url, api_key=api_key, model=model)
        return await engine.synthesize(text, voice, speed=speed or 1.0, http_client=http_client)

    async def speak(self, text: str, lang: Optional[str] = None, voice: Optional[str] = None) -> None:
        """Tổng hợp và phát âm thanh qua loa."""
        if not getattr(settings, "tts_enabled", False):
            return

        clean = clean_text_for_speech(text)
        if not clean:
            return

        # Câu mới thay câu cũ: lấy lượt mới, câu cũ đang tổng hợp dở sẽ bị bỏ khi xong
        self._generation += 1
        my_generation = self._generation
        self._synthesizing += 1
        try:
            # Engine đọc theo khúc (VieNeu) giao từng khúc qua on_chunk → khúc đầu phát ngay, khúc sau xếp hàng;
            # engine khác trả cả bài một lần → cũng đi qua hàng đợi (1 khúc duy nhất)
            audio_data = await self.synthesize(
                text, lang=lang, voice=voice, should_continue=lambda: my_generation == self._generation,
                on_chunk=lambda wav: self._deliver_audio(wav, my_generation))
            if my_generation != self._generation:
                return  # đã có câu mới hơn hoặc người dùng bấm dừng trong lúc tổng hợp
            if audio_data:
                self._deliver_audio(audio_data, my_generation)
            self.playback_started.emit(clean)
        except Exception as exc:
            logger.warning("Lỗi phát giọng nói TTS: %s", exc)
            self.playback_error.emit(str(exc))
        finally:
            self._synthesizing -= 1

    def is_speaking(self) -> bool:
        """Đang phát hoặc đang tổng hợp một câu sẽ phát → click Ted / menu "Dừng đọc" có tác dụng."""
        if self._player_busy() or self._chunk_queue.has_pending:
            return True
        return self._synthesizing > 0 and self._last_stopped_generation != self._generation

    def stop(self) -> None:
        """Dừng phát âm thanh ngay lập tức và huỷ mọi câu đang tổng hợp dở (kể cả các khúc đang xếp hàng)."""
        self._generation += 1
        self._last_stopped_generation = self._generation
        self._chunk_queue.clear()
        self._pcm_stream.stop()
        self._awaiting_playback = False
        self.player.stop()

    def _deliver_audio(self, data: bytes, generation: int) -> None:
        if generation != self._generation:
            return   # khúc muộn của lượt đã bị dừng / bị câu mới thay
        new_turn = generation != self._delivered_generation
        self._delivered_generation = generation
        if self._pcm_stream.append_wav(data, restart=new_turn):
            if new_turn:   # câu mới phát qua luồng PCM: im câu cũ (nếu đang phát qua QMediaPlayer)
                self._chunk_queue.clear()
                self._awaiting_playback = False
                self.player.stop()
            return
        if new_turn:
            self._pcm_stream.stop()
        self._chunk_queue.deliver(data, generation, self._generation)

    def _player_busy(self) -> bool:
        # Sau play() QMediaPlayer mới báo PlayingState một lúc sau → coi "đang nạp để phát" cũng là bận,
        # tránh khúc kế tới đúng lúc đó cắt ngang khúc trước
        return (self._awaiting_playback or self._pcm_stream.is_busy()
                or self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)

    def _on_pcm_stream_finished(self) -> None:
        self._chunk_queue.on_playback_finished(self._generation)   # khúc lỡ rơi về QMediaPlayer vẫn được phát tiếp
        self.playback_finished.emit()

    def _on_media_status_changed(self, status) -> None:
        if status in (QMediaPlayer.MediaStatus.EndOfMedia, QMediaPlayer.MediaStatus.InvalidMedia):
            self._awaiting_playback = False
            self._chunk_queue.on_playback_finished(self._generation)   # hết 1 khúc → phát khúc kế cùng lượt

    def _play_bytes(self, data: bytes) -> None:
        """Lưu audio vào file tạm và nạp vào QMediaPlayer."""
        cache_dir = settings.data_dir / "audio_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        suffix = ".wav" if data[:4] == b"RIFF" else ".mp3"   # Piper trả WAV, server thường trả MP3
        temp_file = cache_dir / f"tts_{stamp}{suffix}"
        temp_file.write_bytes(data)

        # Xoá file cũ trước nếu có
        if self._current_temp_file and self._current_temp_file.exists():
            try:
                self._current_temp_file.unlink(missing_ok=True)
            except OSError:
                pass

        self._current_temp_file = temp_file
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(temp_file)))
        self._awaiting_playback = True   # xoá khi loa báo đang phát / hết bài / lỗi
        self.player.play()

    async def test_connection(
        self,
        server_url: str,
        voice: str,
        test_text: str,
        api_key: str = "",
        model: str = "tts-1",
        speed: float = 1.0,
    ) -> Tuple[bool, str]:
        """Kiểm tra gọi thử giọng nói trực tiếp từ giao diện Cài đặt."""
        try:
            data = await self._synthesize_remote(
                test_text,
                voice=voice,
                server_url=server_url,
                api_key=api_key,
                model=model,
                speed=speed,
            )
            self._play_bytes(data)
            return True, "Kết nối và phát giọng nói thành công!"
        except Exception as exc:
            return False, f"Lỗi TTS: {exc}"

    async def test_offline_voice(self, model_id: str, test_text: str, speed: float = 1.0) -> Tuple[bool, str]:
        """Nghe thử 1 giọng offline đã tải (Cài đặt / ngay sau khi tải xong)."""
        model = get_model(model_id)
        if model is None:
            return False, "Chưa chọn giọng offline."
        try:
            data = await LocalEmbeddedTTSEngine().synthesize(prepare_text_for_speech(test_text), model.id, speed)
            self._play_bytes(data)
            return True, f"Đang phát giọng offline: {model.title}"
        except Exception as exc:
            return False, f"Lỗi TTS offline: {exc}"


# Singleton mặc định dùng cho app
tts_service = TTSService()
