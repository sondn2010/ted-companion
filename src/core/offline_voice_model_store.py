"""Kho mô hình giọng nói offline trong thư mục dữ liệu người dùng (~/.ted/voice_models), KHÔNG nằm trong bộ cài.

Bố cục:
    voice_models/tts/<model_id>/<files>      giọng Piper
    voice_models/stt/<model_id>/<files>      model whisper.cpp
    voice_models/runtime/<tts|stt>/...       binary piper / whisper-cli tải kèm lần đầu

Tải về an toàn: ghi `.part` rồi đổi tên khi xong (không bao giờ để lại file dở), hỗ trợ huỷ, giải nén chống path traversal.
"""

import asyncio
import hashlib
import logging
import os
from pathlib import Path
import shutil
import stat
import tarfile
from typing import Callable, Optional
import zipfile

import httpx

from src.config import settings
from src.core.offline_voice_model_catalog import (
    OfflineVoiceModel,
    VoiceRuntime,
    get_model,
    models_for,
    runtime_for,
)

logger = logging.getLogger("ted")

# progress(bytes_done, bytes_total, label) — total có thể 0 nếu server không trả Content-Length
ProgressCallback = Callable[[int, int, str], None]


class DownloadCancelled(Exception):
    pass


# Mỗi loại (tts/stt) chỉ 1 lượt tải tại 1 thời điểm: 2 popup cùng tải sẽ ghi chung file .part / thư mục bộ chạy
_KIND_LOCKS: dict[str, asyncio.Lock] = {}
_HTTP_TIMEOUT = httpx.Timeout(60.0, read=30.0)   # read ngắn để bấm Huỷ có tác dụng nhanh khi mạng treo


def _kind_lock(kind: str) -> asyncio.Lock:
    return _KIND_LOCKS.setdefault(kind, asyncio.Lock())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def voice_models_root() -> Path:
    return settings.data_dir / "voice_models"


def model_dir(model: OfflineVoiceModel) -> Path:
    return voice_models_root() / model.kind / model.id


def model_main_path(model: OfflineVoiceModel) -> Path:
    return model_dir(model) / model.main_file


def is_model_installed(model: OfflineVoiceModel) -> bool:
    if model.engine == "vieneu":   # không có file model rời: chỉ có file đánh dấu do installer ghi sau khi warmup thành công
        return (model_dir(model) / model.main_file).is_file()
    return all((model_dir(model) / name).is_file() for _url, name in model.files)


def installed_models(kind: str, language: Optional[str] = None) -> list[OfflineVoiceModel]:
    return [m for m in models_for(kind, language) if is_model_installed(m)]


def delete_model(model: OfflineVoiceModel) -> None:
    if model.engine == "vieneu":   # model VieNeu: còn dọn môi trường Python/cache khi không còn model nào dùng
        from src.core.vieneu_runtime_installer import uninstall_vieneu
        uninstall_vieneu(model.id)
        return
    shutil.rmtree(model_dir(model), ignore_errors=True)


def runtime_dir(kind: str) -> Path:
    return voice_models_root() / "runtime" / kind


def find_runtime_executable(kind: str, runtime: Optional[VoiceRuntime] = None) -> Optional[Path]:
    """Ưu tiên binary đã tải vào app; nếu không có thì dò lệnh trong PATH (vd. `brew install whisper-cpp`)."""
    runtime = runtime or runtime_for(kind)
    base = runtime_dir(kind)
    if base.is_dir():
        for candidate in base.rglob(runtime.executable):
            if candidate.is_file():
                return candidate
    for name in runtime.path_names:
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def resolve_model(kind: str, preferred_id: str = "", language: Optional[str] = None) -> Optional[OfflineVoiceModel]:
    """Model đã cài theo id người dùng chọn; nếu chưa chọn/đã xoá thì lấy model đã cài tốt nhất:
    ưu tiên khuyên dùng, rồi chất lượng cao hơn (vd VieNeu Turbo 5★ thắng Piper 4★ khi cả hai đã tải)."""
    model = get_model(preferred_id) if preferred_id else None
    if model and model.kind == kind and is_model_installed(model) and (language is None or model.language == language):
        return model
    candidates = installed_models(kind, language)
    candidates.sort(key=lambda m: (not m.recommended, -m.quality))
    return candidates[0] if candidates else None


def _safe_extract(archive: Path, dest: Path) -> None:
    dest_resolved = dest.resolve()

    def _check(name: str) -> None:
        target = (dest / name).resolve()
        if dest_resolved != target and dest_resolved not in target.parents:
            raise RuntimeError(f"Tệp nén chứa đường dẫn không an toàn: {name}")

    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                _check(name)
            zf.extractall(dest)
    else:
        with tarfile.open(archive, "r:gz") as tf:
            members = tf.getmembers()
            for member in members:
                _check(member.name)
                if member.issym() or member.islnk():
                    _check(os.path.join(os.path.dirname(member.name), member.linkname))
            try:
                tf.extractall(dest, members=members, filter="data")   # Python ≥ 3.11.4: chặn thêm file đặc biệt
            except TypeError:
                tf.extractall(dest, members=members)


async def _download_file(
    client: httpx.AsyncClient, url: str, target: Path, label: str,
    progress: Optional[ProgressCallback], cancel: Optional[asyncio.Event],
    done_before: int = 0, grand_total: int = 0,
) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    written = 0
    try:
        async with client.stream("GET", url, follow_redirects=True) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"Không tải được {label} (HTTP {resp.status_code}).")
            size = int(resp.headers.get("content-length") or 0)
            total = grand_total or size
            with part.open("wb") as fh:
                async for chunk in resp.aiter_bytes(256 * 1024):
                    if cancel is not None and cancel.is_set():
                        raise DownloadCancelled()
                    fh.write(chunk)
                    written += len(chunk)
                    if progress:
                        progress(done_before + written, total, label)
        os.replace(part, target)
        return written
    except BaseException:
        part.unlink(missing_ok=True)
        raise


async def _download_with_retry(*args, attempts: int = 3, **kwargs) -> int:
    """Mạng chập chờn (ReadError / timeout) là chuyện thường với file vài trăm MB → thử lại vài lần."""
    for attempt in range(1, attempts + 1):
        try:
            return await _download_file(*args, **kwargs)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            if attempt == attempts:
                raise RuntimeError(f"Mạng bị gián đoạn khi tải ({type(exc).__name__}).") from exc
            logger.warning("Tải lỗi mạng (%s), thử lại lần %d", type(exc).__name__, attempt + 1)
            await asyncio.sleep(2 * attempt)
    return 0


async def ensure_runtime(
    kind: str, progress: Optional[ProgressCallback] = None, cancel: Optional[asyncio.Event] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Path:
    """Đảm bảo có binary chạy offline. Raise RuntimeError kèm hướng dẫn nếu HĐH không có bản dựng sẵn."""
    runtime = runtime_for(kind)
    existing = find_runtime_executable(kind, runtime)
    if existing:
        return existing
    if not runtime.url:
        raise RuntimeError(runtime.manual_hint or "Hệ điều hành này chưa có bộ chạy offline dựng sẵn.")

    base = runtime_dir(kind)
    archive = base.parent / runtime.url.rsplit("/", 1)[-1]
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=_HTTP_TIMEOUT)
    try:
        await _download_with_retry(client, runtime.url, archive, "bộ chạy offline", progress, cancel)
    finally:
        if owns_client:
            await client.aclose()
    staging = base.with_name(base.name + ".staging")
    try:
        if runtime.sha256 and await asyncio.to_thread(_sha256, archive) != runtime.sha256:
            raise RuntimeError("Bộ chạy tải về không khớp mã kiểm tra (sha256) — đã huỷ để an toàn, hãy thử lại.")
        # Giải nén vào thư mục tạm rồi mới thay thế: giải nén hỏng giữa chừng không để lại bộ chạy "nửa vời"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        await asyncio.to_thread(_safe_extract, archive, staging)
        shutil.rmtree(base, ignore_errors=True)
        os.replace(staging, base)
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
    exe = find_runtime_executable(kind, runtime)
    if exe is None:
        raise RuntimeError("Đã tải bộ chạy nhưng không tìm thấy file thực thi.")
    if os.name != "nt":
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return exe


async def download_model(
    model: OfflineVoiceModel, progress: Optional[ProgressCallback] = None,
    cancel: Optional[asyncio.Event] = None, client: Optional[httpx.AsyncClient] = None,
) -> Path:
    """Tải bộ chạy (nếu thiếu) rồi tải các file model. Trả về đường dẫn file chính của model.
    Model VieNeu (engine="vieneu") đi qua installer riêng (uv + venv + warmup), trả về file đánh dấu đã cài."""
    if model.engine == "vieneu":
        from src.core.vieneu_runtime_installer import install_vieneu
        return await install_vieneu(model, progress, cancel, client)
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=_HTTP_TIMEOUT)
    try:
        async with _kind_lock(model.kind):
            await _download_model_files(model, progress, cancel, client)
    finally:
        if owns_client:
            await client.aclose()
    logger.info("Đã tải mô hình giọng nói offline %s", model.id)
    return model_main_path(model)


async def _download_model_files(model, progress, cancel, client) -> None:
    await ensure_runtime(model.kind, progress, cancel, client=client)
    done = 0
    grand_total = model.size_mb * 1024 * 1024
    for url, name in model.files:
        target = model_dir(model) / name
        if target.is_file():
            continue
        done += await _download_with_retry(client, url, target, model.title, progress, cancel, done, grand_total)
