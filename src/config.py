import json
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import ValidationError

from src.core.connection_registry_and_settings_migration import (
    SETTINGS_SCHEMA_VERSION,
    OpenAIConnection,
    HermesConnection,
    ModuleOverride,
    migrate_settings_payload,
    coerce_setting_value,
    validation_error_summary,
)

from src.core.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    get_character_skins,
    i18n,
    tr,
)
from src.core.character_pack_loader import load_character_pack
from src.core.database_sync.database_sync_config import DatabaseSyncConfig
from src.core.unlockable_skin_pack_loader import load_unlockable_collection
from src.core.version_config import get_default_update_url

logger = logging.getLogger("ted")


# 2 nhân vật hiện nhanh trên menu chuột phải (không dùng submenu)
QUICK_MENU_SKINS = ["cat", "shiba"]

USER_NAME_MAX_LEN = 40

# Các khoá đơn giản được lưu trực tiếp (ngoài connections / modules)
_SIMPLE_KEYS = (
    "character_skin", "active_module", "default_pomodoro_mins", "mindful_ping_mins",
    "ambient_sound_enabled", "language", "update_url",
    "tts_enabled", "tts_mode", "tts_server_url", "tts_api_key", "tts_model",
    "tts_voice_vi", "tts_voice_en", "tts_speed",
    "stt_enabled", "stt_mode", "stt_server_url", "stt_api_key", "stt_model", "stt_language",
    "tts_local_voice_vi", "tts_local_voice_en", "stt_local_model", "character_personas", "tts_configured",
    "vieneu_voice", "vieneu_voices",   # vieneu_voice = khoá cũ (1 giọng chung), chỉ đọc để migrate sang vieneu_voices
    "untangle_nudge_enabled",   # bật/tắt duy nhất của nudge Gỡ Rối thích nghi
    "health_break_prompt_enabled",   # bật/tắt duy nhất của gợi ý vận động nhẹ sau mỗi phiên Deep Work
    "hotkeys",   # chỉ lưu phần override phím tắt: {action_id: {"seq": "Ctrl+Alt+F", "enabled": true}},
    "activity_monitor_enabled",   # bật/tắt theo dõi hoạt động học tập & xao nhãng
    "sleep_reminder_enabled",     # bật/tắt nhắc ngủ sớm & cảnh báo làm việc muộn
    "bedtime_target",             # giờ đi ngủ mục tiêu ("HH:MM", mặc định "23:00")
    "bedtime_warning_mins",       # số phút nhắc trước giờ ngủ (mặc định 15)
    "late_work_nudge_interval_mins", # khoảng cách giữa các lần nhắc khi làm việc muộn (phút, mặc định 30)
    "exercise_reminder_enabled",  # bật/tắt nhắc tập thể dục tại chỗ sau Deep Work
    "exercise_daily_target",      # mục tiêu số lần thể dục mỗi ngày (mặc định 4)
    "database_sync",              # đồng bộ SQLite ⇄ PostgreSQL (không chứa tài khoản/mật khẩu)
    "user_name",                  # tên người dùng máy này (mỗi máy 1 người), "" = chưa hỏi
)


def get_resource_path(relative_path: str) -> Path:
    """Trả về đường dẫn tuyệt đối tới thư mục assets, tương thích cả khi chạy code trực tiếp lẫn khi đóng gói PyInstaller (.exe / .app)."""
    if hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent.parent
    return base_path / relative_path


# Character Pack cài lúc build/dev (scripts/install_character_pack.py --pack <tên>) THAY THẾ 6 con vật mặc định.
# TED_CHARACTER_PACK_DIR: đọc pack từ thư mục khác (test trỏ vào thư mục rỗng để luôn dùng 6 con vật).
CHARACTER_PACK = load_character_pack(
    Path(os.getenv("TED_CHARACTER_PACK_DIR") or get_resource_path("assets/character_pack"))
)
PACK_SKIN_EMOJI = "🎭"   # nhãn luôn bắt đầu bằng emoji (character_display_name tách emoji khỏi tên)

# Toàn bộ danh mục nhân vật Chibi cho phép lựa chọn trong Cấu hình (Dashboard / Settings)
if CHARACTER_PACK is not None:
    CHARACTER_SKINS = {cid: f"{PACK_SKIN_EMOJI} {c.display_name}" for cid, c in CHARACTER_PACK.characters.items()}
    DEFAULT_CHARACTER_SKIN = CHARACTER_PACK.default_character_id
else:
    CHARACTER_SKINS = {
        "cat": "🐱 Mèo Ted (Cat)",
        "shiba": "🐕 Cún Shiba (Shiba)",
        "bunny": "🐰 Thỏ Bông (Bunny)",
        "penguin": "🐧 Cánh Cụt (Penguin)",
        "owl": "🦉 Cú Đêm (Owl)",
        "panda": "🐼 Gấu Trúc (Panda)",
    }
    DEFAULT_CHARACTER_SKIN = "cat"

# Nhân vật bundle mở khoá dần (assets/unlockable_skin_packs, xem README trong thư mục): key `pack/character`,
# điều kiện riêng từng nhân vật. TED_UNLOCKABLE_SKIN_PACKS_DIR: đọc từ thư mục khác (test trỏ vào thư mục rỗng).
_UNLOCKABLE = load_unlockable_collection(
    Path(os.getenv("TED_UNLOCKABLE_SKIN_PACKS_DIR") or get_resource_path("assets/unlockable_skin_packs"))
)
UNLOCKABLE_SKINS = _UNLOCKABLE.skins
UNLOCKABLE_PACK_TITLES = _UNLOCKABLE.pack_titles
# Mọi nhân vật dạng ảnh PNG theo trạng thái: pack `--pack` (key gốc) + nhân vật bundle (key `pack/char`)
PACK_CHARACTERS = {**(CHARACTER_PACK.characters if CHARACTER_PACK is not None else {}), **_UNLOCKABLE.characters}
for _skin in UNLOCKABLE_SKINS:   # key hợp lệ cho settings / MCP (việc khoá do FocusEngine.set_character + skin_unlock_gate)
    CHARACTER_SKINS[_skin.key] = f"{PACK_SKIN_EMOJI} {_UNLOCKABLE.characters[_skin.key].display_name}"

# Icon Cún Shiba dùng chung cho app (cửa sổ, taskbar) và khay hệ thống
APP_ICON_RELATIVE_PATH = "assets/icons/app_icon.png"


class AppConfig:
    """Quản lý cấu hình ứng dụng Ted (schema v2) và lưu trữ tại $TED_HOME/settings.json (mặc định ~/.ted)."""

    def __init__(self, data_dir: Optional[Path] = None):
        load_dotenv()
        self.data_dir = Path(data_dir or os.getenv("TED_HOME") or Path.home() / ".ted")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "ted_local.db"
        self.settings_file = self.data_dir / "settings.json"
        self.ipc_command_file = self.data_dir / "mcp_command_queue.json"

        self.character_skin: str = os.getenv("TED_CHARACTER_SKIN", DEFAULT_CHARACTER_SKIN).lower()
        if self.character_skin not in CHARACTER_SKINS:
            self.character_skin = DEFAULT_CHARACTER_SKIN
        self.connections: list[OpenAIConnection] = []
        self.module_overrides: dict[str, ModuleOverride] = {}
        self.active_module: str = "work"
        self.read_only = False  # True khi file do bản build mới hơn ghi → không được ghi đè
        self._extra: dict = {}  # khoá chưa biết → giữ nguyên khi save (tương thích phiên bản mới hơn)
        # Biến môi trường sai định dạng → dùng mặc định, không làm sập lúc import
        self.default_pomodoro_mins: int = coerce_setting_value(int, os.getenv("DEFAULT_POMODORO_MINUTES"), 25)
        self.default_break_mins: int = coerce_setting_value(int, os.getenv("DEFAULT_SHORT_BREAK_MINUTES"), 5)
        self.mindful_ping_mins: int = coerce_setting_value(int, os.getenv("MINDFUL_PING_INTERVAL_MINUTES"), 15)
        self.ambient_sound_enabled: bool = False
        self.language: str = os.getenv("TED_LANGUAGE", DEFAULT_LANGUAGE).lower()
        if self.language not in SUPPORTED_LANGUAGES:
            self.language = DEFAULT_LANGUAGE
        i18n.set_language(self.language, emit_signal=False)
        self.update_url: str = get_default_update_url()
        self.tts_enabled: bool = coerce_setting_value(bool, os.getenv("TED_TTS_ENABLED"), False)
        self.tts_mode: str = str(os.getenv("TED_TTS_MODE", "auto")).strip().lower()
        self.tts_server_url: str = str(os.getenv("TED_TTS_SERVER_URL", "http://127.0.0.1:8880/v1")).strip()
        self.tts_api_key: str = str(os.getenv("TED_TTS_API_KEY", "")).strip()
        self.tts_model: str = str(os.getenv("TED_TTS_MODEL", "tts-1")).strip()
        self.tts_voice_vi: str = str(os.getenv("TED_TTS_VOICE_VI", "vi-VN-Standard-A")).strip()
        self.tts_voice_en: str = str(os.getenv("TED_TTS_VOICE_EN", "en-US-Standard-C")).strip()
        self.tts_speed: float = coerce_setting_value(float, os.getenv("TED_TTS_SPEED"), 1.0)
        self.stt_enabled: bool = coerce_setting_value(bool, os.getenv("TED_STT_ENABLED"), False)
        self.stt_mode: str = str(os.getenv("TED_STT_MODE", "auto")).strip().lower()
        self.stt_server_url: str = str(os.getenv("TED_STT_SERVER_URL", "http://127.0.0.1:8881/v1")).strip()
        self.stt_api_key: str = str(os.getenv("TED_STT_API_KEY", "")).strip()
        self.stt_model: str = str(os.getenv("TED_STT_MODEL", "whisper-1")).strip()
        self.stt_language: str = str(os.getenv("TED_STT_LANGUAGE", "vi")).strip()
        # Model offline đã tải về (~/.ted/voice_models): id trong offline_voice_model_catalog, "" = tự chọn
        self.tts_local_voice_vi: str = ""
        self.tts_local_voice_en: str = ""
        self.stt_local_model: str = ""
        # Giọng preset của VieNeu-TTS ("" = giọng mặc định của model); danh sách lấy từ sidecar /v1/voices
        self.vieneu_voices: dict = {}   # model_id VieNeu -> id giọng ("" / thiếu = mặc định của model)
        # Tên / tính cách / giọng riêng từng nhân vật (character_persona_profiles), mở bằng click 5 lần lên pet
        self.character_personas: dict = {}
        # Đã từng cấu hình & bật TTS → hiện nút 🔊 bật/tắt nói trong bong bóng chat (kể cả khi đang tắt)
        self.tts_configured: bool = False
        # Override phím tắt toàn cục (global_hotkey_manager); {} = toàn bộ mặc định
        self.hotkeys: dict = {}
        self.untangle_nudge_enabled: bool = True   # Ted gợi ý Gỡ Rối khi user bị kẹt (chỉ bubble, không giọng nói)
        self.health_break_prompt_enabled: bool = True   # hỏi 1 hành động sức khỏe nhỏ sau mỗi phiên Deep Work hoàn thành
        self.activity_monitor_enabled: bool = True   # giám sát học tập và xao nhãng
        self.sleep_reminder_enabled: bool = True     # nhắc ngủ sớm & cảnh báo làm việc muộn
        self.bedtime_target: str = "23:00"           # giờ đi ngủ mục tiêu ("HH:MM")
        self.bedtime_warning_mins: int = 15          # số phút nhắc trước giờ ngủ
        self.late_work_nudge_interval_mins: int = 30 # khoảng cách giữa các lần nhắc khi làm việc muộn
        self.exercise_reminder_enabled: bool = True  # nhắc tập thể dục tại chỗ sau Deep Work
        self.exercise_daily_target: int = 4          # mục tiêu số lần thể dục mỗi ngày (3-4 lần)
        self.database_sync = DatabaseSyncConfig()    # mặc định chỉ lưu cục bộ
        self.user_name: str = ""                     # "" = chưa đặt → hỏi lúc mở app, nói "bạn"
        self.load()

    def set_user_name(self, name: str) -> None:
        self.user_name = str(name or "").strip()[:USER_NAME_MAX_LEN]

    @property
    def user_display_name(self) -> str:
        """Tên Ted gọi người dùng; chưa đặt tên → "bạn" / "you"."""
        return self.user_name or tr("user_name_fallback")

    @property
    def character_display_name(self) -> str:
        skins = get_character_skins(self.language)
        default = skins.get(self.character_skin, CHARACTER_SKINS.get(self.character_skin, CHARACTER_SKINS[DEFAULT_CHARACTER_SKIN]))
        custom = (self.character_personas.get(self.character_skin) or {}).get("name", "")
        if isinstance(custom, str) and custom.strip():   # tên riêng người dùng đặt: giữ emoji của nhân vật
            return f"{default.split(' ', 1)[0]} {custom.strip()[:40]}"
        return default

    # ---------- load / save ----------
    def load(self):
        raw: dict = {}
        if file_exists := self.settings_file.exists():
            try:
                raw = json.loads(self.settings_file.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("settings.json không phải object")
            except Exception as exc:
                # File hỏng: giữ mặc định, không ghi lúc load; sao lưu bản hỏng trước khi lần save sau ghi đè
                logger.error("Không đọc được %s: %s", self.settings_file, exc)
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                try:
                    shutil.copy2(self.settings_file, self.settings_file.with_name(f"settings.json.corrupt-{stamp}"))
                except OSError as copy_exc:  # ổ đĩa đầy / file bị khoá: bỏ qua sao lưu, vẫn khởi động được
                    logger.error("Không sao lưu được file settings hỏng: %s", copy_exc)
                self._apply_payload(migrate_settings_payload({}, os.environ)[0])
                return

        version = raw.get("schema_version")
        if isinstance(version, int) and version > SETTINGS_SCHEMA_VERSION:
            logger.warning("settings.json schema v%s mới hơn bản này (v%s) → chỉ đọc", version, SETTINGS_SCHEMA_VERSION)
            self.read_only = True

        payload, changed = migrate_settings_payload(raw, os.environ)
        self._apply_payload(payload)
        if changed:
            backup = self.settings_file.with_name("settings.json.bak")
            if file_exists and not backup.exists():
                shutil.copy2(self.settings_file, backup)
            try:
                self.save()
            except OSError as exc:  # vd MCP đang migrate cùng lúc / antivirus giữ file
                logger.error("Không lưu được settings sau migrate: %s", exc)

    def _apply_payload(self, payload: dict):
        skin = payload.get("character_skin", self.character_skin)
        if skin in CHARACTER_SKINS:
            self.character_skin = skin
        self.active_module = str(payload.get("active_module") or "work")
        self.default_pomodoro_mins = coerce_setting_value(int, payload.get("default_pomodoro_mins"), self.default_pomodoro_mins)
        self.mindful_ping_mins = coerce_setting_value(int, payload.get("mindful_ping_mins"), self.mindful_ping_mins)
        self.ambient_sound_enabled = coerce_setting_value(bool, payload.get("ambient_sound_enabled"), self.ambient_sound_enabled)
        lang = payload.get("language", self.language)
        if lang in SUPPORTED_LANGUAGES:
            self.language = lang
            i18n.set_language(self.language, emit_signal=False)
        self.update_url = str(payload.get("update_url") or get_default_update_url()).strip()
        self.tts_enabled = coerce_setting_value(bool, payload.get("tts_enabled"), self.tts_enabled)
        self.tts_mode = str(payload.get("tts_mode") or "auto").strip().lower()
        self.tts_server_url = str(payload.get("tts_server_url") or "http://127.0.0.1:8880/v1").strip()
        self.tts_api_key = str(payload.get("tts_api_key") or "").strip()
        self.tts_model = str(payload.get("tts_model") or "tts-1").strip()
        self.tts_voice_vi = str(payload.get("tts_voice_vi") or "vi-VN-Standard-A").strip()
        self.tts_voice_en = str(payload.get("tts_voice_en") or "en-US-Standard-C").strip()
        self.tts_speed = coerce_setting_value(float, payload.get("tts_speed"), self.tts_speed)
        self.stt_enabled = coerce_setting_value(bool, payload.get("stt_enabled"), self.stt_enabled)
        self.stt_mode = str(payload.get("stt_mode") or "auto").strip().lower()
        self.stt_server_url = str(payload.get("stt_server_url") or "http://127.0.0.1:8881/v1").strip()
        self.stt_api_key = str(payload.get("stt_api_key") or "").strip()
        self.stt_model = str(payload.get("stt_model") or "whisper-1").strip()
        self.stt_language = str(payload.get("stt_language") or "vi").strip()
        self.tts_local_voice_vi = str(payload.get("tts_local_voice_vi") or self.tts_local_voice_vi).strip()
        self.tts_local_voice_en = str(payload.get("tts_local_voice_en") or self.tts_local_voice_en).strip()
        self.stt_local_model = str(payload.get("stt_local_model") or self.stt_local_model).strip()
        raw_voices = payload.get("vieneu_voices")
        self.vieneu_voices = ({str(k): str(v).strip() for k, v in raw_voices.items() if k and v}
                              if isinstance(raw_voices, dict) else {})
        legacy_voice = str(payload.get("vieneu_voice") or "").strip()   # bản cũ: 1 giọng dùng chung mọi model VieNeu
        if legacy_voice and not self.vieneu_voices:
            # gán cho model VieNeu đang chọn (nếu có), không thì Turbo; sai thì sidecar tự rơi về giọng mặc định
            key = self.tts_local_voice_vi if self.tts_local_voice_vi.startswith("vieneu-") else "vieneu-v3-turbo"
            self.vieneu_voices[key] = legacy_voice
        self.tts_configured = coerce_setting_value(bool, payload.get("tts_configured"), self.tts_configured)
        self.untangle_nudge_enabled = coerce_setting_value(bool, payload.get("untangle_nudge_enabled"), True)
        self.health_break_prompt_enabled = coerce_setting_value(bool, payload.get("health_break_prompt_enabled"), True)
        self.activity_monitor_enabled = coerce_setting_value(bool, payload.get("activity_monitor_enabled"), True)
        self.sleep_reminder_enabled = coerce_setting_value(bool, payload.get("sleep_reminder_enabled"), True)
        self.bedtime_target = str(payload.get("bedtime_target") or "23:00").strip()
        self.bedtime_warning_mins = coerce_setting_value(int, payload.get("bedtime_warning_mins"), 15)
        self.late_work_nudge_interval_mins = coerce_setting_value(int, payload.get("late_work_nudge_interval_mins"), 30)
        self.exercise_reminder_enabled = coerce_setting_value(bool, payload.get("exercise_reminder_enabled"), True)
        self.exercise_daily_target = coerce_setting_value(int, payload.get("exercise_daily_target"), 4)
        self.set_user_name(payload.get("user_name") or "")
        try:
            self.database_sync = DatabaseSyncConfig.model_validate(payload.get("database_sync") or {})
        except ValidationError as exc:
            logger.warning("Bỏ qua cấu hình đồng bộ dữ liệu: %s", validation_error_summary(exc))
            self.database_sync = DatabaseSyncConfig()
        raw_hotkeys = payload.get("hotkeys")
        self.hotkeys = ({str(k): v for k, v in raw_hotkeys.items() if isinstance(v, dict)}   # bỏ mục sai kiểu
                        if isinstance(raw_hotkeys, dict) else {})
        personas = payload.get("character_personas")
        self.character_personas = {k: v for k, v in personas.items() if isinstance(v, dict)} if isinstance(personas, dict) else {}
        self.connections = []
        for item in payload.get("connections") or []:
            try:
                self.connections.append(OpenAIConnection.model_validate(item))
            except ValidationError as exc:
                logger.warning("Bỏ qua kết nối không hợp lệ %r: %s", item.get("id") if isinstance(item, dict) else "?", validation_error_summary(exc))
        if not self.connections:  # luôn có ít nhất 1 kết nối để client pool không bao giờ rỗng
            seed = migrate_settings_payload({}, os.environ)[0]["connections"]
            self.connections = [OpenAIConnection.model_validate(c) for c in seed]
        self.module_overrides = {}
        for module_id, item in (payload.get("modules") or {}).items():
            try:
                self.module_overrides[module_id] = ModuleOverride.model_validate(item or {})
            except ValidationError as exc:
                logger.warning("Bỏ qua cấu hình module %s: %s", module_id, validation_error_summary(exc))
        known = set(_SIMPLE_KEYS) | {"schema_version", "connections", "modules"}
        self._extra = {k: v for k, v in payload.items() if k not in known}

    def save(self):
        if self.read_only:
            logger.warning("Bỏ qua save(): settings.json thuộc bản build mới hơn")
            return
        payload = dict(self._extra)
        payload.update({
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "character_skin": self.character_skin,
            "connections": [c.model_dump() for c in self.connections],
            "modules": {k: v.model_dump(exclude_none=True) for k, v in self.module_overrides.items()},
            "active_module": self.active_module,
            "default_pomodoro_mins": self.default_pomodoro_mins,
            "mindful_ping_mins": self.mindful_ping_mins,
            "ambient_sound_enabled": self.ambient_sound_enabled,
            "user_name": self.user_name,
            "language": self.language,
            "update_url": self.update_url,
            "tts_enabled": self.tts_enabled,
            "tts_mode": self.tts_mode,
            "tts_server_url": self.tts_server_url,
            "tts_api_key": self.tts_api_key,
            "tts_model": self.tts_model,
            "tts_voice_vi": self.tts_voice_vi,
            "tts_voice_en": self.tts_voice_en,
            "tts_speed": self.tts_speed,
            "tts_local_voice_vi": self.tts_local_voice_vi,
            "tts_local_voice_en": self.tts_local_voice_en,
            "stt_enabled": self.stt_enabled,
            "stt_mode": self.stt_mode,
            "stt_server_url": self.stt_server_url,
            "stt_api_key": self.stt_api_key,
            "stt_model": self.stt_model,
            "stt_language": self.stt_language,
            "stt_local_model": self.stt_local_model,
            "character_personas": self.character_personas,
            "tts_configured": self.tts_configured,
            "vieneu_voices": self.vieneu_voices,
            "hotkeys": self.hotkeys,
            "untangle_nudge_enabled": self.untangle_nudge_enabled,
            "health_break_prompt_enabled": self.health_break_prompt_enabled,
            "activity_monitor_enabled": self.activity_monitor_enabled,
            "sleep_reminder_enabled": self.sleep_reminder_enabled,
            "bedtime_target": self.bedtime_target,
            "bedtime_warning_mins": self.bedtime_warning_mins,
            "late_work_nudge_interval_mins": self.late_work_nudge_interval_mins,
            "exercise_reminder_enabled": self.exercise_reminder_enabled,
            "exercise_daily_target": self.exercise_daily_target,
            "database_sync": self.database_sync.to_payload(),
        })
        # Ghi nguyên tử: file tạm + os.replace để không bao giờ để lại settings.json dở dang
        fd, tmp_name = tempfile.mkstemp(dir=self.data_dir, prefix="settings.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, indent=2, ensure_ascii=False))
            os.replace(tmp_name, self.settings_file)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    # ---------- connections CRUD ----------
    def get_connection(self, conn_id: str) -> Optional[OpenAIConnection]:
        return next((c for c in self.connections if c.id == conn_id), None)

    def upsert_connection(self, conn: OpenAIConnection):
        for idx, existing in enumerate(self.connections):
            if existing.id == conn.id:
                self.connections[idx] = conn
                return
        self.connections.append(conn)

    def delete_connection(self, conn_id: str) -> Optional[str]:
        """Xoá kết nối. Trả về chuỗi lỗi nếu bị từ chối, None nếu thành công."""
        if self.get_connection(conn_id) is None:
            return f"Không tìm thấy kết nối '{conn_id}'."
        if len(self.connections) <= 1:
            return "Phải giữ lại ít nhất 1 kết nối AI."
        users = [m for m, o in self.module_overrides.items() if o.connection == conn_id and o.enabled is not False]
        if users:
            return f"Kết nối '{conn_id}' đang được dùng bởi module: {', '.join(users)}."
        self.connections = [c for c in self.connections if c.id != conn_id]
        return None

    # ---------- module overrides ----------
    def module_override(self, module_id: str) -> ModuleOverride:
        return self.module_overrides.get(module_id) or ModuleOverride()

    def set_module_override(self, module_id: str, **fields):
        current = self.module_override(module_id).model_dump()
        current.update(fields)
        self.module_overrides[module_id] = ModuleOverride.model_validate(current)


settings = AppConfig()
