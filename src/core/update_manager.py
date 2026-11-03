"""
Mô-đun quản lý cập nhật ứng dụng Ted Companion:
- Kiểm tra phiên bản mới từ máy chủ lưu trữ (asynchronous HTTP).
- Tải ngầm file thực thi mới về thư mục tạm và kiểm tra SHA256.
- Lưu trạng thái bản cập nhật sẵn sàng cài đặt khi thoát ứng dụng.
"""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
import sys
from typing import Callable, Optional

import httpx

from src.config import settings
from src.core.background_task_spawner import spawn_background_task
from src.core.i18n import tr
from src.core.version_config import APP_VERSION, is_newer_version

logger = logging.getLogger("ted")


@dataclass
class UpdateInfo:
    """Thông tin bản cập nhật mới từ remote version.json."""

    version: str
    release_date: str = ""
    changelog: str = ""
    url: str = ""
    sha256: Optional[str] = None
    size: Optional[int] = None
    platform_key: str = "windows"
    file_name: str = "pending_update.exe"


class UpdateManager:
    """Xử lý kiểm tra, tải ngầm và lưu trữ các bản cập nhật của Ted."""

    def __init__(self, updates_dir: Optional[Path] = None):
        self.updates_dir = Path(updates_dir or (settings.data_dir / "updates"))
        self.ready_file = self.updates_dir / "update_ready.json"

    @staticmethod
    def get_current_platform() -> str:
        if sys.platform == "win32":
            return "windows"
        if sys.platform == "darwin":
            return "macos"
        return "linux"

    async def check_for_updates(
        self,
        update_url: str,
        current_version: str = APP_VERSION,
        timeout_sec: float = 6.0,
    ) -> Optional[UpdateInfo]:
        """
        Kiểm tra từ xa xem có bản cập nhật mới hay không.
        Trả về UpdateInfo nếu có bản mới hơn cho nền tảng hiện tại, ngược lại trả về None.
        """
        url = (update_url or "").strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            logger.debug("URL cập nhật không hợp lệ: %r", url)
            return None

        try:
            async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            if not isinstance(data, dict):
                logger.warning("Nội dung version.json không phải là JSON object")
                return None

            remote_ver = str(data.get("version") or "").strip()
            if not remote_ver or not is_newer_version(remote_ver, current_version):
                logger.debug("Không có bản mới hơn (Hiện tại: %s, Server: %s)", current_version, remote_ver)
                return None

            platforms = data.get("platforms") or {}
            plat_key = self.get_current_platform()
            plat_data = platforms.get(plat_key)

            if not plat_data or not isinstance(plat_data, dict):
                logger.warning("Không tìm thấy thông tin tải cho nền tảng '%s' trong version.json", plat_key)
                return None

            download_url = str(plat_data.get("url") or "").strip()
            if not download_url:
                logger.warning("Thông tin nền tảng '%s' thiếu trường 'url'", plat_key)
                return None

            file_ext = ".exe" if plat_key == "windows" else ".zip"
            file_name = f"pending_update{file_ext}"

            return UpdateInfo(
                version=remote_ver,
                release_date=str(data.get("release_date") or ""),
                changelog=str(data.get("changelog") or data.get("release_notes") or ""),
                url=download_url,
                sha256=plat_data.get("sha256"),
                size=plat_data.get("size"),
                platform_key=plat_key,
                file_name=file_name,
            )
        except Exception as exc:
            logger.warning("Lỗi khi kiểm tra cập nhật từ %s: %s", url, exc)
            return None

    async def download_update(
        self,
        info: UpdateInfo,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        """
        Tải file cập nhật trong nền về thư mục updates, kiểm tra checksum SHA256 và lưu trạng thái sẵn sàng.
        """
        self.updates_dir.mkdir(parents=True, exist_ok=True)
        final_file = self.updates_dir / info.file_name
        tmp_file = self.updates_dir / f"{info.file_name}.tmp"

        if tmp_file.exists():
            tmp_file.unlink(missing_ok=True)

        hasher = hashlib.sha256() if info.sha256 else None
        downloaded_bytes = 0
        total_bytes = info.size or 0

        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            async with client.stream("GET", info.url) as resp:
                resp.raise_for_status()
                headers = getattr(resp, "headers", {}) or {}
                content_len = headers.get("Content-Length")
                if content_len and content_len.isdigit():
                    total_bytes = int(content_len)

                with open(tmp_file, "wb") as fh:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        if chunk:
                            fh.write(chunk)
                            downloaded_bytes += len(chunk)
                            if hasher:
                                hasher.update(chunk)
                            if progress_callback:
                                progress_callback(downloaded_bytes, total_bytes)

        # Kiểm tra tính toàn vẹn (SHA256) nếu có
        if hasher and info.sha256:
            computed = hasher.hexdigest().lower()
            expected = info.sha256.strip().lower()
            if computed != expected:
                tmp_file.unlink(missing_ok=True)
                raise ValueError(f"Mã băm SHA256 không khớp! Nhận: {computed}, Mong đợi: {expected}")

        # Đổi tên file tạm thành file chính
        if final_file.exists():
            final_file.unlink(missing_ok=True)
        tmp_file.replace(final_file)

        # Ghi trạng thái update sẵn sàng
        ready_state = {
            "version": info.version,
            "platform": info.platform_key,
            "file_path": str(final_file.resolve()),
            "sha256": info.sha256,
            "downloaded_at": datetime.now().isoformat(),
        }
        self.ready_file.write_text(json.dumps(ready_state, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Đã tải xong bản cập nhật v%s tại %s", info.version, final_file)
        return final_file

    def get_pending_update(self) -> Optional[dict]:
        """Trả về thông tin bản cập nhật đang chờ cài đặt nếu file tồn tại hợp lệ."""
        if not self.ready_file.exists():
            return None
        try:
            data = json.loads(self.ready_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            target_path = Path(data.get("file_path", ""))
            if target_path.exists() and target_path.is_file():
                return data
            return None
        except Exception as exc:
            logger.warning("Không đọc được %s: %s", self.ready_file, exc)
            return None

    def clear_pending_update(self) -> None:
        """Xoá file update sẵn sàng và các file tạm trong thư mục updates."""
        try:
            if self.ready_file.exists():
                self.ready_file.unlink(missing_ok=True)
            for file in self.updates_dir.glob("pending_update*"):
                file.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Lỗi khi dọn dẹp thư mục updates: %s", exc)

    async def run_startup_update_flow(
        self,
        bubble,
        update_url: Optional[str] = None,
    ) -> None:
        """Kiểm tra bản cập nhật và hiện lời nhắc trên bong bóng thoại của Ted nếu có bản mới."""
        url = (update_url or settings.update_url or "").strip()
        if not url:
            return

        info = await self.check_for_updates(url, current_version=APP_VERSION)
        if not info:
            return

        def on_accept():
            bubble.show_message(tr("update_downloading"), mood="CHEER", timeout_ms=3500)
            spawn_background_task(self._bg_download(info, bubble), name="bg_update_download")

        def on_later():
            bubble.hide()

        actions = [
            (tr("update_btn_accept"), on_accept),
            (tr("update_btn_later"), on_later),
        ]
        msg = tr("update_prompt_bubble", version=info.version)
        bubble.show_message(msg, mood="CHEER", actions=actions, timeout_ms=0)

    async def _bg_download(self, info: UpdateInfo, bubble) -> None:
        try:
            await self.download_update(info)
            bubble.show_message(
                tr("update_downloaded_ready", version=info.version),
                mood="CHEER",
                timeout_ms=7000,
            )
        except Exception as exc:
            logger.error("Lỗi tải bản cập nhật: %s", exc)
            bubble.show_message(
                tr("update_download_failed", error=str(exc)),
                mood="GENTLE_NUDGE",
                timeout_ms=6000,
            )

    def trigger_exit_update(self, relaunch: bool = True) -> bool:
        """Kiểm tra và kích hoạt kịch bản áp dụng bản cập nhật khi thoát app."""
        ready = self.get_pending_update()
        if not ready:
            return False
        file_path = ready.get("file_path")
        if not file_path:
            return False
        from src.core.exit_updater import apply_update_on_exit

        return apply_update_on_exit(
            pending_file=Path(file_path),
            updates_dir=self.updates_dir,
            relaunch=relaunch,
        )


update_manager = UpdateManager()
