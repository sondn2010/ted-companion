"""
Kịch bản tự động cập nhật khi người dùng đóng ứng dụng Ted Companion:
- Sinh script nền độc lập (detached process).
- Chờ tiến trình Ted hiện tại giải phóng hoàn toàn file lock.
- Ghi đè file thực thi mới và tự động khởi chạy lại Ted Companion mới.
"""

import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import Optional

logger = logging.getLogger("ted")

WINDOWS_BAT_TEMPLATE = """@echo off
setlocal
set PID=%~1
set TARGET=%~2
set UPDATE=%~3
set RELAUNCH=%~4

set /a count=0
:wait_loop
tasklist /fi "PID eq %PID%" 2>nul | findstr /i "%PID%" >nul
if errorlevel 1 goto apply_update
timeout /t 1 /nobreak >nul
set /a count+=1
if %count% geq 35 goto apply_update
goto wait_loop

:apply_update
:: Ghi de file moi vao vi tri file cu
copy /y "%UPDATE%" "%TARGET%" >nul
del /f /q "%UPDATE%" 2>nul

:: Khoi chay lai Ted moi neu duoc yeu cau
if "%RELAUNCH%"=="1" (
    start "" "%TARGET%"
)

:: Tu huy script
(goto) 2>nul & del "%~f0"
"""

MACOS_SH_TEMPLATE = """#!/bin/bash
PID="$1"
TARGET="$2"
UPDATE="$3"
RELAUNCH="$4"

# Cho tien trinh cu thoat han
for i in {1..35}; do
    if ! kill -0 "$PID" 2>/dev/null; then
        break
    fi
    sleep 1
done

# Neu file update la zip, giai nen vao thu muc chua App bundle
if [[ "$UPDATE" == *.zip ]]; then
    APP_DIR="$(dirname "$TARGET")"
    if [[ "$TARGET" == *".app/Contents/MacOS"* ]]; then
        APP_DIR="${TARGET%%.app*}.app"
    fi
    PARENT_DIR="$(dirname "$APP_DIR")"
    unzip -q -o "$UPDATE" -d "$PARENT_DIR"
    rm -f "$UPDATE"
else
    cp -f "$UPDATE" "$TARGET"
    chmod +x "$TARGET"
    rm -f "$UPDATE"
fi

if [ "$RELAUNCH" = "1" ]; then
    if [[ "$TARGET" == *".app"* ]]; then
        APP_PATH="${TARGET%%.app*}.app"
        open "$APP_PATH"
    else
        "$TARGET" &
    fi
fi

rm -f "$0"
"""


def generate_windows_updater_script(script_path: Path) -> str:
    """Tạo file batch hỗ trợ cập nhật nền trên Windows."""
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(WINDOWS_BAT_TEMPLATE, encoding="utf-8")
    return WINDOWS_BAT_TEMPLATE


def generate_macos_updater_script(script_path: Path) -> str:
    """Tạo file shell script hỗ trợ cập nhật nền trên macOS."""
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(MACOS_SH_TEMPLATE, encoding="utf-8")
    try:
        os.chmod(script_path, 0o755)
    except Exception:
        pass
    return MACOS_SH_TEMPLATE


def apply_update_on_exit(
    executable_path: Optional[Path] = None,
    pending_file: Optional[Path] = None,
    updates_dir: Optional[Path] = None,
    pid: Optional[int] = None,
    relaunch: bool = True,
) -> bool:
    """
    Kích hoạt tiến trình cập nhật ngầm độc lập khi thoát app.
    Trả về True nếu đã khởi chạy tiến trình updater, False nếu đang ở chế độ dev hoặc thiếu file.
    """
    is_frozen = getattr(sys, "frozen", False)
    if not is_frozen:
        logger.info(
            "Ứng dụng đang chạy ở chế độ mã nguồn (dev mode). "
            "Bỏ qua ghi đè nhị phân khi thoát (file cập nhật vẫn lưu trong thư mục updates)."
        )
        return False

    target_exe = Path(executable_path or sys.executable).resolve()
    target_update = Path(pending_file) if pending_file else None

    if not target_update or not target_update.exists():
        logger.warning("Không tìm thấy file cập nhật đang chờ: %s", target_update)
        return False

    current_pid = pid or os.getpid()
    work_dir = Path(updates_dir or target_update.parent)
    work_dir.mkdir(parents=True, exist_ok=True)

    relaunch_flag = "1" if relaunch else "0"

    try:
        if sys.platform == "win32":
            script_path = work_dir / "update_helper.bat"
            generate_windows_updater_script(script_path)

            DETACHED_PROCESS = 0x00000008
            CREATE_NO_WINDOW = 0x08000000

            cmd = [
                "cmd.exe",
                "/c",
                str(script_path),
                str(current_pid),
                str(target_exe),
                str(target_update),
                relaunch_flag,
            ]
            subprocess.Popen(
                cmd,
                creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
                close_fds=True,
            )
            logger.info("Đã kích hoạt update_helper.bat nền để cập nhật và khởi động lại sau khi thoát.")
            return True

        else:
            script_path = work_dir / "update_helper.sh"
            generate_macos_updater_script(script_path)

            cmd = [
                "/bin/bash",
                str(script_path),
                str(current_pid),
                str(target_exe),
                str(target_update),
                relaunch_flag,
            ]
            subprocess.Popen(
                cmd,
                start_new_session=True,
                close_fds=True,
            )
            logger.info("Đã kích hoạt update_helper.sh nền để cập nhật và khởi động lại sau khi thoát.")
            return True

    except Exception as exc:
        logger.error("Không thể khởi chạy updater nền khi thoát: %s", exc)
        return False
