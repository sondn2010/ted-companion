"""Engine TTS VieNeu: bảo đảm sidecar đang chạy rồi gọi RemoteOpenAITTSEngine tới 127.0.0.1 (token ngẫu nhiên làm api_key).

- Văn bản đi qua vieneu_story_preprocessor (ngắt nghỉ theo ngữ cảnh, dấu câu, từ điển phát âm) thành từng segment;
  mỗi segment (≤ ~350 ký tự) đọc tuần tự (timeout riêng), nối khoảng lặng theo `pause_after` rồi ghép thành 1 WAV.
  `should_continue()` (TTSService truyền vào) trả False → bỏ các khúc còn lại (người dùng bấm dừng / có câu mới hơn).
- Timeout / đứt kết nối → manager.mark_unhealthy → lần sau dựng lại sidecar thay vì chờ một tiến trình treo.
- httpx với trust_env=False: lưu lượng loopback không bao giờ đi qua proxy (chỉ áp dụng cho sidecar, server remote giữ nguyên).
API cho UI:
    await list_vieneu_voices(model_id) -> list[VieneuVoice]   # đọc cache tĩnh lúc cài; không có cache mới hỏi sidecar
Giọng đang dùng lấy từ settings.vieneu_voices[model_id] ("" / thiếu = giọng mặc định của model).
"""

import asyncio
import logging
from typing import Callable, Optional

import httpx

from src.config import settings
from src.core.tts_service import BaseTTSEngine, RemoteOpenAITTSEngine
from src.core.vieneu_sidecar_process_manager import VieneuSidecarManager, vieneu_sidecar_manager
from src.core.vieneu_story_preprocessor import effective_pauses, preprocess
from src.core.vieneu_text_chunking_and_wav_concat import append_silence, concat_wav_bytes, split_text_for_tts
from src.core.vieneu_voice_list_cache import VieneuVoice, parse_voices_payload, read_cached_voices

logger = logging.getLogger("ted")

__all__ = ["VieneuSidecarTTSEngine", "VieneuVoice", "list_vieneu_voices"]

_CHUNK_TIMEOUT_S = 60.0   # mỗi khúc ≤ 350 ký tự: CPU yếu vài giây → vài chục giây
_FIRST_CHUNK_CHARS = 100  # khúc đầu khi phát theo khúc: có tiếng sau ~1–3 giây
_STREAM_CHUNK_CHARS = 160  # các khúc sau khi phát theo khúc (~1–2 câu)


class VieneuSidecarTTSEngine(BaseTTSEngine):
    def __init__(self, model_id: str, manager: Optional[VieneuSidecarManager] = None):
        self.model_id = model_id
        self.manager = manager or vieneu_sidecar_manager

    async def synthesize(self, text: str, voice: str, speed: float = 1.0,
                         http_client: Optional[httpx.AsyncClient] = None,
                         should_continue: Optional[Callable[[], bool]] = None,
                         on_chunk: Optional[Callable[[bytes], None]] = None) -> bytes:
        """Trả WAV đã ghép; b"" nếu `should_continue()` báo dừng giữa chừng (người gọi bỏ qua kết quả).
        Có `on_chunk`: giao từng khúc WAV ngay khi tổng hợp xong (phát sớm, không chờ hết bài) và trả b""."""
        # `voice` do TTSService truyền là id model (Piper-style) → giọng VieNeu lấy từ settings riêng từng model
        chunks = _plan_chunks(text, streaming=on_chunk is not None)
        if not chunks:
            raise ValueError("Văn bản rỗng.")
        endpoint = await asyncio.to_thread(self.manager.ensure_running, self.model_id)
        voices = getattr(settings, "vieneu_voices", None) or {}
        sidecar_voice = voices.get(self.model_id, "")
        remote = RemoteOpenAITTSEngine(server_url=endpoint.base_url, api_key=endpoint.token, model="vieneu")
        client = http_client or httpx.AsyncClient(timeout=_CHUNK_TIMEOUT_S, trust_env=False)
        wavs: list[bytes] = []
        try:
            for chunk, speed_factor, pause in chunks:
                if should_continue is not None and not should_continue():
                    return b""
                try:
                    wav = await remote.synthesize(chunk, sidecar_voice, speed * speed_factor, http_client=client)
                except httpx.TransportError:   # timeout / đứt kết nối: sidecar có thể đã treo
                    self.manager.mark_unhealthy(endpoint)
                    raise
                if pause > 0:
                    wav = append_silence(wav, pause)
                if on_chunk is not None:
                    if should_continue is None or should_continue():
                        on_chunk(wav)
                else:
                    wavs.append(wav)
        finally:
            if http_client is None:
                await client.aclose()
        return concat_wav_bytes(wavs) if wavs else b""


def _plan_chunks(text: str, streaming: bool) -> list[tuple[str, float, float]]:
    """Văn bản → [(khúc gửi model, hệ số tốc độ, giây lặng nối sau)] theo bộ tiền xử lý ngắt nghỉ.
    Mỗi segment (≈1 câu / vế) là một lượt suy luận — đo trên CPU: tổng thời gian bằng gộp câu, nhưng nghỉ đúng tới ms.
    Segment dài vẫn cắt theo giới hạn ký tự cũ (không nghỉ thêm giữa các mẩu). Phát theo khúc: khúc đầu ≤ ~1 câu ngắn
    để có tiếng ngay; các khúc sau ~1–2 câu vì Turbo trên CPU tổng hợp chậm xấp xỉ thời gian đọc."""
    segments = preprocess(text)
    plan: list[tuple[str, float, float]] = []
    for seg, pause in zip(segments, effective_pauses(segments)):
        if streaming:
            parts = split_text_for_tts(seg.text, limit=_STREAM_CHUNK_CHARS, first_limit=0 if plan else _FIRST_CHUNK_CHARS)
        else:
            parts = split_text_for_tts(seg.text)
        if parts:
            plan += [(p, seg.speed, 0.0) for p in parts[:-1]] + [(parts[-1], seg.speed, pause)]
    return plan


async def prewarm_vieneu_if_selected(manager: Optional[VieneuSidecarManager] = None) -> bool:
    """Khởi động sẵn sidecar lúc mở app nếu giọng Việt đang dùng là VieNeu (lần nói đầu khỏi chờ ~5 giây nạp model).
    Lỗi chỉ ghi log: lần nói thật sẽ tự thử lại."""
    from src.core.offline_voice_model_store import resolve_model
    from src.core.tts_service import tts_service
    if not getattr(settings, "tts_enabled", False) or tts_service.get_effective_mode() != "embedded":
        return False
    model = resolve_model("tts", tts_service.pick_voice("vi"), "vi")
    if model is None or model.engine != "vieneu":
        return False
    try:
        await asyncio.to_thread((manager or vieneu_sidecar_manager).ensure_running, model.id)
        return True
    except Exception as exc:
        logger.warning("Không khởi động sẵn được VieNeu: %s", exc)
        return False


async def list_vieneu_voices(model_id: str, manager: Optional[VieneuSidecarManager] = None) -> list[VieneuVoice]:
    cached = read_cached_voices(model_id)
    if cached is not None:
        return cached
    # Cài bản cũ chưa có cache: hỏi sidecar, nhưng KHÔNG đá sidecar đang chạy của model khác (đang đọc dở)
    manager = manager or vieneu_sidecar_manager
    running = manager.running_model_id()
    if running not in (None, model_id):
        raise RuntimeError("Chưa có danh sách giọng của model này — hãy tải lại model để lưu danh sách.")
    endpoint = await asyncio.to_thread(manager.ensure_running, model_id)
    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        resp = await client.get(f"{endpoint.base_url}/voices", headers={"Authorization": f"Bearer {endpoint.token}"})
    if resp.status_code != 200:
        raise RuntimeError(f"Không lấy được danh sách giọng VieNeu (HTTP {resp.status_code}).")
    return parse_voices_payload(resp.json())
