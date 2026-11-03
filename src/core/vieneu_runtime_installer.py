"""Cài VieNeu-TTS offline ngay trong app: uv (sha256 ghim) → venv Python 3.12 → `vieneu==3.8.3` → warmup (tải model HF).

API cho UI (cùng hình dạng với offline_voice_model_store):
    await install_vieneu(model, progress, cancel)   progress(done, total, label): uv = byte thật; các bước sau (0, 0, "[n/4] ...")
    is_vieneu_installed(model_id) / uninstall_vieneu(model_id)
Idempotent: bước nào xong rồi thì bỏ qua. Huỷ/lỗi ở bước venv/pip → xoá venv dở. Log mọi lệnh con ở vieneu_env/logs.
Chuỗi cung ứng: `uv pip install --exclude-newer` đóng băng toàn bộ phụ thuộc bắc cầu; warmup tải model theo revision đã ghim
(vieneu_sidecar/vieneu_hf_revision_pins.py) và ghi cache danh sách giọng (voices_<mode>.json).
Gỡ cài đặt: chặn sidecar khởi động lại, xoá file đánh dấu venv TRƯỚC, xoá file nặng trên luồng nền (`uninstall_vieneu_async`).
"""

import asyncio
import json
import logging
from pathlib import Path
import shutil
import time
from typing import Optional

import httpx

from src.core.offline_voice_model_catalog import OFFLINE_VOICE_MODELS, VIENEU_MARKER_FILE, OfflineVoiceModel, get_model
from src.core.offline_voice_model_store import (
    DownloadCancelled, ProgressCallback, _kind_lock, ensure_runtime, is_model_installed, model_dir, runtime_dir,
)
from src.core.vieneu_installer_command_runner import LONG_TIMEOUT_S, run_logged_command  # noqa: F401  (re-export cho test)
from src.core.vieneu_runtime_paths import (
    PKG_MARKER_NAME, SIDECAR_MODE_BY_MODEL_ID, VIENEU_EXCLUDE_NEWER, VIENEU_PACKAGE_SPEC, VIENEU_PYTHON_VERSION,
    check_env_path_length, log_dir, sidecar_script_path, venv_dir, venv_is_usable, venv_python, vieneu_env_dir,
    vieneu_subprocess_env, voices_cache_file,
)

logger = logging.getLogger("ted")

_STAGE_COUNT = 4


def _marker_path(model: OfflineVoiceModel) -> Path:
    return model_dir(model) / VIENEU_MARKER_FILE


def is_vieneu_installed(model_id: str) -> bool:
    model = get_model(model_id)
    return bool(model and model.engine == "vieneu" and is_model_installed(model) and venv_is_usable())


async def _run(cmd: list[str], cancel, env: dict, log_name: str, timeout_s: float = LONG_TIMEOUT_S) -> None:
    await asyncio.to_thread(run_logged_command, cmd, env, log_dir() / log_name, cancel, timeout_s)


def _report(progress: Optional[ProgressCallback], step: int, text: str) -> None:
    if progress:
        progress(0, 0, f"[{step}/{_STAGE_COUNT}] {text}")


async def install_vieneu(
    model: OfflineVoiceModel, progress: Optional[ProgressCallback] = None,
    cancel: Optional[asyncio.Event] = None, client: Optional[httpx.AsyncClient] = None,
) -> Path:
    """Cài đủ chuỗi cho 1 model VieNeu. Trả về đường dẫn file đánh dấu. Raise DownloadCancelled khi huỷ."""
    mode = SIDECAR_MODE_BY_MODEL_ID.get(model.id)
    if model.engine != "vieneu" or mode is None:
        raise ValueError(f"{model.id} không phải model VieNeu.")
    async with _kind_lock("vieneu"):
        if is_vieneu_installed(model.id):
            return _marker_path(model)
        check_env_path_length()   # fail-fast trước khi tải uv / cài thư viện
        env = vieneu_subprocess_env()
        _report(progress, 1, "Tải công cụ uv")
        uv = await ensure_runtime("vieneu", progress, cancel, client=client)
        try:
            await _ensure_env_and_package(uv, env, progress, cancel)
        except BaseException:
            shutil.rmtree(venv_dir(), ignore_errors=True)   # không để môi trường dở dang
            raise
        _report(progress, 4, f"Tải và thử giọng {model.title} (lần đầu, vài phút)")
        await _run([str(venv_python()), str(sidecar_script_path()), "--mode", mode, "--warmup",
                    "--voices-file", str(voices_cache_file(mode))], cancel, env, "vieneu_warmup.log")
        marker = _marker_path(model)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"package": VIENEU_PACKAGE_SPEC, "mode": mode, "installed_at": int(time.time())}),
                          encoding="utf-8")
    logger.info("Đã cài VieNeu-TTS %s", model.id)
    return marker


async def _ensure_env_and_package(uv: Path, env: dict, progress, cancel) -> None:
    pkg_marker = vieneu_env_dir() / PKG_MARKER_NAME
    if not (venv_python().is_file() and pkg_marker.is_file() and pkg_marker.read_text(encoding="utf-8") == VIENEU_PACKAGE_SPEC):
        # Venv thiếu / dở dang / khác phiên bản: dựng lại từ đầu (xoá file đánh dấu trước để không bao giờ "tin nhầm")
        pkg_marker.unlink(missing_ok=True)
        shutil.rmtree(venv_dir(), ignore_errors=True)
        _report(progress, 2, f"Tạo môi trường Python {VIENEU_PYTHON_VERSION}")
        await _run([str(uv), "venv", "--managed-python", "--python", VIENEU_PYTHON_VERSION, str(venv_dir())],
                   cancel, env, "vieneu_env_create.log", timeout_s=900)
        _report(progress, 3, "Cài thư viện VieNeu (khoảng 500 MB, có thể vài phút)")
        await _run([str(uv), "pip", "install", "--python", str(venv_python()), "--exclude-newer", VIENEU_EXCLUDE_NEWER,
                    VIENEU_PACKAGE_SPEC], cancel, env, "vieneu_pip.log")
        pkg_marker.write_text(VIENEU_PACKAGE_SPEC, encoding="utf-8")   # ghi CUỐI: có file này ⇔ venv đã cài xong
        shutil.rmtree(vieneu_env_dir() / "uv_cache", ignore_errors=True)   # venv đã hardlink/copy xong: bỏ cache ~600 MB


def uninstall_vieneu(model_id: str) -> None:
    """Xoá model; khi không còn model VieNeu nào thì xoá luôn môi trường Python + cache HF + uv. ĐỒNG BỘ (nặng):
    UI dùng `uninstall_vieneu_async`. Chặn sidecar khởi động lại và tắt nó trước (Windows khoá file đang chạy)."""
    model = get_model(model_id)
    if model is None or model.engine != "vieneu":
        return
    from src.core.vieneu_sidecar_process_manager import vieneu_sidecar_manager
    vieneu_sidecar_manager.disable()
    try:
        vieneu_sidecar_manager.stop()
        shutil.rmtree(model_dir(model), ignore_errors=True)
        if not any(m.engine == "vieneu" and is_model_installed(m) for m in OFFLINE_VOICE_MODELS):
            (vieneu_env_dir() / PKG_MARKER_NAME).unlink(missing_ok=True)   # xoá TRƯỚC: xoá dở thì venv bị coi là hỏng
            shutil.rmtree(vieneu_env_dir(), ignore_errors=True)
            shutil.rmtree(runtime_dir("vieneu"), ignore_errors=True)
    finally:
        vieneu_sidecar_manager.enable()


async def uninstall_vieneu_async(model_id: str) -> None:
    """Gỡ trên luồng nền (hàng chục nghìn file ~1.4 GB) để UI không đứng."""
    await asyncio.to_thread(uninstall_vieneu, model_id)
