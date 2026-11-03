"""Tính cách + tên + giọng nói RIÊNG cho từng nhân vật (mèo, cú, gấu trúc, shiba, thỏ, cánh cụt) — chỉ cấu hình phía app.

KHÔNG đụng prompt của Hermes (não ở Hermes). Persona chỉ đổi những gì app tự làm:
- Tên hiển thị (header bong bóng chat, sidebar Dashboard).
- Câu cửa miệng khi click đơn lên pet (trộn với pool câu động viên của module).
- Giọng TTS riêng: giọng máy chủ (vi/en), giọng offline đã tải (vi/en), tốc độ đọc.

Mở cấu hình: click nhanh 5 lần lên nhân vật (hành động ẩn — ghi trong tab Trợ giúp).
Lưu trong settings.json → khoá `character_personas` {skin: {...}}. Nhân vật chưa lưu persona thì app chạy như cũ.
Ngoại lệ: nhân vật của Character Pack có sẵn persona trong characters.json (tên, voice_config, catchphrases,
expressions) → áp dụng ngay cả khi chưa lưu; người dùng lưu đè thì phần đã lưu thắng.
"""

from dataclasses import asdict, dataclass, field
from typing import Optional

from src.config import CHARACTER_SKINS, PACK_CHARACTERS, settings


@dataclass(frozen=True)
class Personality:
    key: str
    title: str
    description: str
    greeting: str
    catchphrases: tuple[str, ...]
    suggested_speed: float = 1.0


PERSONALITIES: tuple[Personality, ...] = (
    Personality("cheerful", "😄 Vui vẻ, lạc quan", "Luôn tươi cười, nhìn mặt tích cực của mọi chuyện.",
                "Hello hello! {name} có mặt rồi đây!",
                ("Cười lên nào, việc khó mấy cũng xong thôi!", "{name} thấy bạn đang làm rất tốt đó!",
                 "Một bước nhỏ nữa thôi, cố lên!"), 1.05),
    Personality("calm_wise", "🦉 Điềm tĩnh, thông thái", "Chậm rãi, sâu sắc, hay nhắc hít thở và suy nghĩ kỹ.",
                "{name} đây. Mình cùng bình tĩnh bắt đầu nhé.",
                ("Chậm mà chắc, từng bước một thôi.", "Hít một hơi thật sâu... rồi làm tiếp nào.",
                 "Hiểu bản chất quan trọng hơn làm nhanh."), 0.9),
    Personality("energetic", "⚡ Năng động, nhiệt huyết", "Tràn đầy năng lượng, thích thử thách và cổ vũ mạnh mẽ.",
                "Yo! {name} sẵn sàng bứt phá cùng bạn!",
                ("Tăng tốc nào, mình làm được!", "Thêm 1 Pomodoro nữa là phá đảo luôn!",
                 "{name} cổ vũ bạn hết mình đây!"), 1.15),
    Personality("sweet", "🌸 Dễ thương, ngọt ngào", "Nhẹ nhàng, hay khen và an ủi, như một người bạn thân.",
                "Hihi, {name} nhớ bạn quá à!",
                ("Bạn giỏi lắm luôn á!", "Mệt thì nghỉ xíu nha, {name} đợi bạn.", "Ôm bạn một cái thật chặt nè!"), 1.05),
    Personality("funny", "🤪 Hài hước, tinh nghịch", "Hay pha trò nhẹ nhàng cho đỡ căng thẳng.",
                "Ting ting! {name} giao hàng niềm vui tới rồi!",
                ("Bài này khó á? Để {name} doạ nó giùm!", "Tập trung như mèo rình chuột nào!",
                 "Làm xong việc này mình thưởng trà sữa tưởng tượng nha!"), 1.1),
    Personality("disciplined", "🎯 Nghiêm túc, kỷ luật", "Gọn gàng, đúng giờ, nhắc mục tiêu rõ ràng.",
                "{name} báo cáo: sẵn sàng làm việc.",
                ("Tập trung vào 1 việc duy nhất.", "Hoàn thành trước, hoàn hảo sau.",
                 "Đúng giờ là tôn trọng chính mình."), 1.0),
    Personality("gentle", "🌿 Dịu dàng, ân cần", "Nhẹ nhàng, chu đáo, luôn lắng nghe và thấu hiểu.",
                "{name} đây, nhẹ nhàng đồng hành cùng bạn nhé.",
                ("Mọi thứ sẽ ổn thôi, đừng lo lắng nhé.", "Thả lỏng một chút rồi chúng mình tiếp tục nào.",
                 "Bạn làm rất tốt, {name} luôn ở đây ủng hộ bạn."), 0.95),
    Personality("confident", "✨ Tự tin, bản lĩnh", "Quyết đoán, đĩnh đạc, dám nghĩ dám làm và truyền cảm hứng.",
                "{name} đã sẵn sàng bứt phá mọi mục tiêu!",
                ("Tập trung cao độ và dẫn đầu cuộc chơi!", "Không gì có thể làm khó chúng ta hôm nay!",
                 "Bản lĩnh tạo nên sự khác biệt!"), 1.1),
    Personality("analytical", "🧠 Sắc sảo, logic", "Tập trung cao độ, phân tích mạch lạc, tư duy logic và khoa học.",
                "{name} đã sẵn sàng phân tích và giải quyết bài toán.",
                ("Phân tích kỹ lưỡng, hành động chuẩn xác.", "Tập trung vào mấu chốt của vấn đề.",
                 "Từng giả thuyết một, chúng ta sẽ có đáp án tối ưu."), 1.0),
)


@dataclass
class CharacterPersona:
    skin: str
    name: str
    personality: str = "cheerful"
    use_own_voice: bool = True
    voice_vi: str = ""          # giọng máy chủ tiếng Việt
    voice_en: str = ""          # giọng máy chủ tiếng Anh
    local_voice_vi: str = ""    # id giọng offline đã tải
    local_voice_en: str = ""
    speed: float = 1.0
    extra: dict = field(default_factory=dict)   # Character Pack: {"catchphrases": [...], "expressions": {state: [...]}}

    @property
    def personality_profile(self) -> Personality:
        return get_personality(self.personality)

    def greeting(self) -> str:
        return self.personality_profile.greeting.format(name=self.name)

    def catchphrases(self) -> list[str]:
        if self.extra.get("catchphrases"):   # câu riêng của nhân vật trong pack (không chứa {name})
            return list(self.extra["catchphrases"])
        return [line.format(name=self.name) for line in self.personality_profile.catchphrases]

    def mood_lines(self, state: str) -> list[str]:
        """Câu thoại theo trạng thái (idle/focus/cheer/rest/nudge) — chỉ nhân vật Character Pack có."""
        return list((self.extra.get("expressions") or {}).get(state, []))


# Gợi ý mặc định khi mở popup lần đầu (chưa lưu thì KHÔNG áp dụng). Giọng máy chủ để trống = theo cấu hình chung
# (mỗi máy chủ có bộ voice khác nhau); giọng offline id không có trên máy → tự chọn giọng đã tải.
DEFAULT_PERSONAS: dict[str, CharacterPersona] = {
    "cat": CharacterPersona("cat", "Ted", "cheerful", True, "", "",
                            "piper-vi-vais1000-medium", "piper-en-amy-medium", 1.05),
    "owl": CharacterPersona("owl", "Cú Thông Thái", "calm_wise", True, "", "",
                            "piper-vi-vais1000-medium", "piper-en-ryan-medium", 0.9),
    "panda": CharacterPersona("panda", "Pao Pao", "sweet", True, "", "",
                              "piper-vi-25hours-low", "piper-en-lessac-medium", 0.95),
    "shiba": CharacterPersona("shiba", "Shiba Lửa", "energetic", True, "", "",
                              "piper-vi-vais1000-medium", "piper-en-ryan-medium", 1.15),
    "bunny": CharacterPersona("bunny", "Bông", "sweet", True, "", "",
                              "piper-vi-25hours-low", "piper-en-amy-medium", 1.1),
    "penguin": CharacterPersona("penguin", "Pin Pin", "funny", True, "", "",
                                "piper-vi-vais1000-medium", "piper-en-lessac-medium", 1.05),
}

_FIELDS = ("name", "personality", "use_own_voice", "voice_vi", "voice_en", "local_voice_vi", "local_voice_en", "speed")


def get_personality(key: str) -> Personality:
    return next((p for p in PERSONALITIES if p.key == key), PERSONALITIES[0])


def _pack_persona(skin: str) -> Optional[CharacterPersona]:
    """Persona dựng từ characters.json của Character Pack (None nếu skin không thuộc pack)."""
    character = PACK_CHARACTERS.get(skin)
    if character is None:
        return None
    voice = character.voice_config
    try:
        speed = max(0.5, min(2.0, float(voice.get("speed", 1.0))))
    except (TypeError, ValueError):
        speed = 1.0
    known = any(p.key == character.personality_key for p in PERSONALITIES)
    personality = character.personality_key if known else PERSONALITIES[0].key
    # Giọng máy chủ để trống = theo Cài đặt chung: voice_vi/voice_en trong pack là tên giọng edge-tts/OpenAI,
    # máy chủ TTS khác có thể không có. Giọng offline id chưa tải → tự chọn giọng đã tải.
    return CharacterPersona(
        skin, character.display_name[:40], personality, True, "", "",
        str(voice.get("local_voice_vi") or ""), str(voice.get("local_voice_en") or ""), speed,
        {"catchphrases": list(character.catchphrases), "expressions": dict(character.expressions)},
    )


def default_persona(skin: str) -> CharacterPersona:
    base = _pack_persona(skin) or DEFAULT_PERSONAS.get(skin) or CharacterPersona(skin, CHARACTER_SKINS.get(skin, skin))
    return CharacterPersona(**asdict(base))


def saved_persona(skin: Optional[str] = None) -> Optional[CharacterPersona]:
    """Persona người dùng ĐÃ LƯU cho nhân vật (None = chưa cấu hình → app giữ hành vi mặc định).
    Nhân vật Character Pack chưa lưu → persona từ characters.json."""
    skin = skin or settings.character_skin
    raw = (getattr(settings, "character_personas", None) or {}).get(skin)
    if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
        return _pack_persona(skin)   # nhân vật pack: persona trong characters.json là mặc định
    persona = default_persona(skin)
    for key in _FIELDS:
        if key in raw:
            setattr(persona, key, raw[key])
    persona.use_own_voice = persona.use_own_voice is True or str(persona.use_own_voice).lower() in ("true", "1")
    try:
        persona.speed = max(0.5, min(2.0, float(persona.speed)))
    except (TypeError, ValueError):
        persona.speed = 1.0
    persona.name = str(persona.name).strip()[:40]
    return persona


def persona_for_editing(skin: str) -> CharacterPersona:
    return saved_persona(skin) or default_persona(skin)


def save_persona(persona: CharacterPersona) -> None:
    personas = dict(getattr(settings, "character_personas", None) or {})
    personas[persona.skin] = {key: getattr(persona, key) for key in _FIELDS}
    settings.character_personas = personas
    settings.save()


def reset_persona(skin: str) -> None:
    personas = dict(getattr(settings, "character_personas", None) or {})
    personas.pop(skin, None)
    settings.character_personas = personas
    settings.save()


def active_voice_override() -> Optional[CharacterPersona]:
    """Persona của nhân vật đang hiện, nếu người dùng bật 'giọng riêng' cho nhân vật đó."""
    persona = saved_persona()
    return persona if persona is not None and persona.use_own_voice else None
