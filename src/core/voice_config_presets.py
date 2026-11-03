"""Bộ cấu hình mẫu (preset) cho TTS / STT: chọn 1 preset trong popup tìm kiếm → app điền sẵn mọi ô cấu hình.

Mỗi preset chỉ chứa giá trị cho các khoá settings (`values`), không tự lưu — người dùng bấm Thử / Lưu sau khi xem lại.
- `requires_models`: preset offline cần các model này đã tải (popup sẽ gợi ý tải trước).
- `needs_api_key`: dịch vụ đám mây — giữ nguyên API key người dùng đã nhập, chỉ nhắc điền nếu còn trống.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
import unicodedata

GROUP_OFFLINE = "💻 Chạy trên máy (offline)"
GROUP_LOCAL_SERVER = "🐳 Máy chủ nội bộ (Docker)"
GROUP_CLOUD = "☁️ Dịch vụ đám mây"

EDGE_TTS_URL = "http://127.0.0.1:5050/v1"      # travisvn/openai-edge-tts
KOKORO_URL = "http://127.0.0.1:8880/v1"        # docker-compose.voice.yml
VIENEU_DOCKER_URL = "http://localhost:8000/v1"  # VieNeu-TTS `--profile api-cpu` (apps/openai_speech.py, cổng 8000)
FASTER_WHISPER_URL = "http://127.0.0.1:8881/v1"
OPENAI_URL = "https://api.openai.com/v1"
GROQ_URL = "https://api.groq.com/openai/v1"


@dataclass(frozen=True)
class VoiceConfigPreset:
    id: str
    kind: str                    # "tts" | "stt"
    group: str
    title: str
    description: str
    values: dict[str, Any]
    keywords: str = ""
    requires_models: tuple[str, ...] = field(default_factory=tuple)
    needs_api_key: bool = False
    recommended: bool = False

    def search_blob(self) -> str:
        return fold_accents(" ".join((self.title, self.description, self.group, self.keywords)))


def fold_accents(text: str) -> str:
    """'Giọng nữ' → 'giong nu': tìm kiếm không cần gõ dấu."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").lower()


def _tts_offline(pid, title, desc, vi, en, speed=1.0, keywords="", recommended=False):
    return VoiceConfigPreset(
        pid, "tts", GROUP_OFFLINE, title, desc,
        {"tts_mode": "embedded", "tts_local_voice_vi": vi, "tts_local_voice_en": en, "tts_speed": speed},
        keywords=f"offline piper khong can mang {keywords}", requires_models=(vi, en), recommended=recommended,
    )


def _tts_server(pid, group, title, desc, url, model, vi, en, speed=1.0, keywords="", api_key=None):
    values = {"tts_mode": "server", "tts_server_url": url, "tts_model": model,
              "tts_voice_vi": vi, "tts_voice_en": en, "tts_speed": speed}
    if api_key is not None:
        values["tts_api_key"] = api_key
    return VoiceConfigPreset(pid, "tts", group, title, desc, values, keywords=keywords,
                             needs_api_key=group == GROUP_CLOUD)


def _stt_offline(pid, title, desc, model_id, language="vi", keywords="", recommended=False):
    return VoiceConfigPreset(
        pid, "stt", GROUP_OFFLINE, title, desc,
        {"stt_mode": "embedded", "stt_local_model": model_id, "stt_language": language},
        keywords=f"offline whisper khong can mang {keywords}", requires_models=(model_id,), recommended=recommended,
    )


def _stt_server(pid, group, title, desc, url, model, language="vi", keywords="", api_key=None):
    values = {"stt_mode": "server", "stt_server_url": url, "stt_model": model, "stt_language": language}
    if api_key is not None:
        values["stt_api_key"] = api_key
    return VoiceConfigPreset(pid, "stt", group, title, desc, values, keywords=keywords,
                             needs_api_key=group == GROUP_CLOUD)


VOICE_CONFIG_PRESETS: tuple[VoiceConfigPreset, ...] = (
    # ======================= TTS — OFFLINE =======================
    _tts_offline("tts-offline-standard", "Ted chuẩn — nữ rõ chữ (offline)",
                 "Giọng nữ đọc rõ ràng, tốc độ vừa phải. Lựa chọn an toàn cho mọi người.",
                 "piper-vi-vais1000-medium", "piper-en-lessac-medium", 1.0, "mac dinh chuan nu", recommended=True),
    _tts_offline("tts-offline-student-slow", "Đọc chậm cho học sinh (offline)",
                 "Đọc chậm 0.85x, dễ theo kịp khi nghe giảng bài, đọc đề toán.",
                 "piper-vi-vais1000-medium", "piper-en-lessac-medium", 0.85, "hoc sinh cham thcs cap 2 on tap"),
    _tts_offline("tts-offline-natural", "Giọng nữ tự nhiên (offline)",
                 "Ngữ điệu tự nhiên hơn, phù hợp trò chuyện thư giãn.",
                 "piper-vi-25hours-low", "piper-en-amy-medium", 1.0, "tu nhien tro chuyen"),
    _tts_offline("tts-offline-energetic", "Năng động, cổ vũ (offline)",
                 "Đọc nhanh 1.15x, tươi vui — hợp khởi động Pomodoro.",
                 "piper-vi-vais1000-medium", "piper-en-amy-medium", 1.15, "nang dong nhanh co vu pomodoro"),
    _tts_offline("tts-offline-english-listening", "Luyện nghe tiếng Anh — giọng nam (offline)",
                 "Tiếng Anh giọng nam Ryan, chậm 0.9x để luyện nghe; tiếng Việt giữ giọng chuẩn.",
                 "piper-vi-vais1000-medium", "piper-en-ryan-medium", 0.9, "tieng anh luyen nghe nam english"),
    _tts_offline("tts-offline-light", "Siêu nhẹ cho máy yếu (offline)",
                 "Giọng dung lượng nhỏ nhất (28MB), chạy mượt trên máy cũ.",
                 "piper-vi-vivos-xlow", "piper-en-lessac-medium", 1.0, "may yeu nhe nho cu"),
    # ======================= TTS — DOCKER NỘI BỘ =======================
    _tts_server("tts-edge-female", GROUP_LOCAL_SERVER, "Edge-TTS — nữ Hoài My",
                "Giọng Microsoft Neural tiếng Việt rất tự nhiên. Chạy Docker `travisvn/openai-edge-tts` cổng 5050.",
                EDGE_TTS_URL, "tts-1", "vi-VN-HoaiMyNeural", "en-US-AvaNeural", 1.0, "edge microsoft nu hoai my neural",
                api_key="your_api_key_here"),
    _tts_server("tts-edge-male", GROUP_LOCAL_SERVER, "Edge-TTS — nam Nam Minh",
                "Giọng nam tiếng Việt trầm ấm, tự nhiên (Microsoft Neural).",
                EDGE_TTS_URL, "tts-1", "vi-VN-NamMinhNeural", "en-US-AndrewNeural", 0.95, "edge microsoft nam minh neural",
                api_key="your_api_key_here"),
    _tts_server("tts-edge-student", GROUP_LOCAL_SERVER, "Edge-TTS — đọc chậm cho học sinh",
                "Giọng Hoài My đọc chậm 0.85x, giọng Anh trẻ em Ana.",
                EDGE_TTS_URL, "tts-1", "vi-VN-HoaiMyNeural", "en-US-AnaNeural", 0.85, "edge hoc sinh cham thcs",
                api_key="your_api_key_here"),
    _tts_server("tts-kokoro-local", GROUP_LOCAL_SERVER, "Kokoro (docker-compose.voice.yml)",
                "Máy chủ Kokoro có sẵn trong dự án (cổng 8880). Lưu ý: Kokoro CHƯA hỗ trợ tiếng Việt, hợp tiếng Anh.",
                KOKORO_URL, "kokoro", "af_heart", "af_heart", 1.0, "kokoro docker tieng anh", api_key=""),
    # model: server VieNeu bỏ qua trường này; voice: PHẢI là tên giọng có thật (sai → 400), "Hải Đăng" là giọng mặc định
    _tts_server("tts-vieneu-docker", GROUP_LOCAL_SERVER, "VieNeu-TTS (Docker, CPU)",
                "Giọng Việt tự nhiên nhất qua Docker (cổng 8000). Cần tự dựng container từ repo VieNeu — xem hướng dẫn "
                "trong docs/SPEECH_TTS_STT_DEVELOPMENT_GUIDE.md. Không muốn dùng Docker: tải giọng VieNeu offline ở mục Offline.",
                VIENEU_DOCKER_URL, "vieneu-v3-turbo", "Hải Đăng", "Hải Đăng", 1.0,
                "vieneu tieng viet docker cpu tu nhien viet", api_key=""),
    # ======================= TTS — ĐÁM MÂY =======================
    _tts_server("tts-openai-nova", GROUP_CLOUD, "OpenAI — nữ trẻ Nova",
                "Giọng nữ trẻ, ngọt ngào; đọc được tiếng Việt. Cần API key OpenAI (tính phí theo ký tự).",
                OPENAI_URL, "gpt-4o-mini-tts", "nova", "nova", 1.0, "openai gpt nu tre nova"),
    _tts_server("tts-openai-onyx", GROUP_CLOUD, "OpenAI — nam trầm Onyx",
                "Giọng nam trầm ấm, đọc chậm 0.9x. Cần API key OpenAI.",
                OPENAI_URL, "gpt-4o-mini-tts", "onyx", "onyx", 0.9, "openai gpt nam tram onyx"),
    _tts_server("tts-openai-alloy", GROUP_CLOUD, "OpenAI — trung tính Alloy",
                "Giọng trung tính, rõ ràng cho công việc. Cần API key OpenAI.",
                OPENAI_URL, "gpt-4o-mini-tts", "alloy", "alloy", 1.0, "openai gpt trung tinh alloy cong viec"),
    # ======================= STT — OFFLINE =======================
    _stt_offline("stt-offline-small-vi", "Nhận giọng tiếng Việt chính xác (offline)",
                 "Whisper Small — nghe tiếng Việt tốt, hợp đa số máy tính.", "whisper-small-q5", "vi",
                 "tieng viet chinh xac small", recommended=True),
    _stt_offline("stt-offline-base-vi", "Nhận giọng nhanh, cân bằng (offline)",
                 "Whisper Base — nhanh, đủ dùng cho câu lệnh ngắn.", "whisper-base-q5", "vi", "nhanh can bang base"),
    _stt_offline("stt-offline-tiny", "Siêu nhẹ cho máy yếu (offline)",
                 "Whisper Tiny — nhẹ nhất, có thể sai dấu tiếng Việt.", "whisper-tiny-q5", "vi", "may yeu nhe tiny"),
    _stt_offline("stt-offline-turbo", "Chính xác cao nhất — máy mạnh (offline)",
                 "Whisper Large v3 Turbo — chính xác nhất, cần máy ≥ 8GB RAM.", "whisper-large-v3-turbo-q5", "vi",
                 "chinh xac cao large turbo may manh"),
    _stt_offline("stt-offline-english", "Luyện nói tiếng Anh (offline)",
                 "Whisper Small nhận tiếng Anh — luyện phát âm, nói câu.", "whisper-small-q5", "en",
                 "tieng anh english luyen noi phat am"),
    # ======================= STT — MÁY CHỦ =======================
    _stt_server("stt-faster-whisper-local", GROUP_LOCAL_SERVER, "Faster-Whisper (docker-compose.voice.yml)",
                "Máy chủ STT có sẵn trong dự án (cổng 8881), model small.",
                FASTER_WHISPER_URL, "Systran/faster-whisper-small", "vi", "docker faster whisper noi bo", api_key=""),
    _stt_server("stt-openai-whisper", GROUP_CLOUD, "OpenAI Whisper",
                "Nhận giọng đám mây ổn định. Cần API key OpenAI.", OPENAI_URL, "whisper-1", "vi", "openai whisper"),
    _stt_server("stt-openai-gpt4o-mini", GROUP_CLOUD, "OpenAI GPT-4o mini Transcribe",
                "Chính xác hơn Whisper, giá rẻ. Cần API key OpenAI.", OPENAI_URL, "gpt-4o-mini-transcribe", "vi",
                "openai gpt 4o mini transcribe"),
    _stt_server("stt-groq-turbo", GROUP_CLOUD, "Groq Whisper Large v3 Turbo",
                "Rất nhanh, có gói miễn phí. Cần API key Groq.", GROQ_URL, "whisper-large-v3-turbo", "vi",
                "groq nhanh mien phi turbo"),
)


def presets_for(kind: str) -> list[VoiceConfigPreset]:
    return [p for p in VOICE_CONFIG_PRESETS if p.kind == kind]


def get_preset(preset_id: str) -> Optional[VoiceConfigPreset]:
    return next((p for p in VOICE_CONFIG_PRESETS if p.id == preset_id), None)


def search_presets(kind: str, query: str) -> list[VoiceConfigPreset]:
    """Mọi từ trong `query` (không dấu, không phân biệt hoa thường) phải xuất hiện trong preset."""
    words = fold_accents(query).split()
    return [p for p in presets_for(kind) if all(w in p.search_blob() for w in words)]
