"""Đường dẫn & biến môi trường của môi trường chạy VieNeu-TTS (uv + venv Python 3.12 + cache Hugging Face).

Bố cục (mọi thứ nằm trong ~/.ted, không cài gì ra ngoài hệ thống):
    voice_models/runtime/vieneu/            binary `uv` (do offline_voice_model_store.ensure_runtime tải, sha256 ghim)
    voice_models/runtime/vieneu_env/venv    venv Python 3.12 chứa `vieneu`
    voice_models/runtime/vieneu_env/python  Python do uv tải về (UV_PYTHON_INSTALL_DIR)
    voice_models/runtime/vieneu_env/hf      cache model Hugging Face (HF_HOME)
    voice_models/runtime/vieneu_env/logs    log cài đặt / sidecar để chẩn đoán
"""

import os
from pathlib import Path

from src.config import get_resource_path
from src.core.offline_voice_model_store import voice_models_root

VIENEU_PACKAGE_SPEC = "vieneu==3.8.3"   # ghim phiên bản: API SDK thay đổi giữa các bản
VIENEU_EXCLUDE_NEWER = "2026-10-01T00:00:00Z"   # đóng băng việc resolve phụ thuộc: bỏ mọi bản phát hành sau mốc này (sau khi vieneu 3.8.3 ra 2026-09-23)
PKG_MARKER_NAME = "vieneu_package.ok"   # ghi CUỐI cùng khi venv + thư viện đã xong; xoá ĐẦU TIÊN khi gỡ
VIENEU_PYTHON_VERSION = "3.12"          # onnxruntime có wheel cho 3.12; Python dev của Ted (3.15) thì chưa
SIDECAR_RELATIVE_PATH = "src/core/vieneu_sidecar/vieneu_openai_speech_sidecar.py"


SIDECAR_MODE_BY_MODEL_ID = {"vieneu-v3-turbo": "turbo", "vieneu-v3-nano": "nano"}


def vieneu_env_dir() -> Path:
    return voice_models_root() / "runtime" / "vieneu_env"


MAX_WINDOWS_ENV_PATH_CHARS = 80   # + đường dẫn snapshot HF (~160 ký tự) + site-packages lồng sâu phải < MAX_PATH 260


def check_env_path_length(env_dir: Path | None = None, windows: bool | None = None) -> None:
    """Windows: đường dẫn môi trường quá dài → báo lỗi sớm (thay vì cài 15 phút rồi mới hỏng khi nạp DLL)."""
    windows = (os.name == "nt") if windows is None else windows
    env_dir = env_dir or vieneu_env_dir()
    if windows and len(str(env_dir)) > MAX_WINDOWS_ENV_PATH_CHARS:
        raise RuntimeError(
            f"Đường dẫn lưu giọng đọc quá dài ({len(str(env_dir))} ký tự): {env_dir}\n"
            "Windows sẽ không nạp được thư viện Python. Hãy đặt biến môi trường TED_HOME sang thư mục ngắn hơn "
            "(ví dụ C:\\ted) rồi mở lại Ted và tải lại.")


def venv_dir() -> Path:
    return vieneu_env_dir() / "venv"


def venv_python() -> Path:
    return venv_dir() / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def venv_is_usable() -> bool:
    """Venv dùng được = có python VÀ file đánh dấu (ghi cuối khi cài xong). Venv xoá dở mất file đánh dấu trước."""
    return venv_python().is_file() and (vieneu_env_dir() / PKG_MARKER_NAME).is_file()


def voices_cache_file(mode: str) -> Path:
    """Danh sách giọng của model, do `sidecar --warmup` ghi lúc cài → UI chọn giọng không cần chạy sidecar."""
    return vieneu_env_dir() / f"voices_{mode}.json"


def hf_home_dir() -> Path:
    return vieneu_env_dir() / "hf"


def log_dir() -> Path:
    return vieneu_env_dir() / "logs"


def sidecar_script_path() -> Path:
    """File sidecar đi kèm app (PyInstaller: được đóng gói qua `datas` trong TedCompanion.spec)."""
    return get_resource_path(SIDECAR_RELATIVE_PATH)


# Biến môi trường làm yếu chuỗi cung ứng / TLS: luôn bỏ khỏi tiến trình con. Giữ UV_INDEX_URL / UV_DEFAULT_INDEX /
# HF_ENDPOINT / SSL_CERT_FILE vì mirror & CA nội bộ của doanh nghiệp là hợp lệ (xem docs §2b).
_STRIPPED_ENV = (
    "VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "UV_INSECURE_HOST", "UV_INSECURE_NO_ZIP_VALIDATION",
    "UV_EXTRA_INDEX_URL", "UV_FIND_LINKS", "UV_CONSTRAINT", "UV_OVERRIDE", "UV_BUILD_CONSTRAINT",
)


def vieneu_subprocess_env(extra: dict | None = None, offline: bool = False) -> dict:
    """Môi trường con: uv/HF chỉ ghi vào thư mục runtime, không dùng cache/Python toàn cục của người dùng.
    offline=True (chạy sidecar sau khi cài): không gọi Hugging Face — dùng đúng snapshot đã ghim trong cache."""
    env = {k: v for k, v in os.environ.items() if k.upper() not in _STRIPPED_ENV}
    env.update({
        "UV_PYTHON_INSTALL_DIR": str(vieneu_env_dir() / "python"),
        "UV_CACHE_DIR": str(vieneu_env_dir() / "uv_cache"),
        "UV_NO_CONFIG": "1",
        "HF_HOME": str(hf_home_dir()),
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        env.pop(key, None)   # biến offline có sẵn của người dùng không được làm hỏng bước tải model
    if offline:
        env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    env.update(extra or {})
    return env
