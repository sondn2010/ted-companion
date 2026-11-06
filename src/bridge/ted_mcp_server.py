#!/usr/bin/env python3
"""
Ted FastMCP Server — Cho phép các AI Agent hoặc công cụ MCP trực tiếp điều khiển
giao diện PySide6 của Ted, đổi nhân vật (Mèo / Cú / Gấu trúc), quản lý Tasks, Pomodoro và Daily Journal.
"""

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastmcp import FastMCP
from src.config import CHARACTER_SKINS, DEFAULT_CHARACTER_SKIN, settings
from src.core.models import db

mcp = FastMCP("ted-companion-tools")


def _enqueue_ui_command(payload: dict):
    """Gửi lệnh sang tiến trình giao diện PySide6 qua hàng đợi IPC JSON."""
    cmd_file = settings.ipc_command_file
    queue = []
    if cmd_file.exists():
        try:
            existing = json.loads(cmd_file.read_text(encoding="utf-8"))
            queue = existing if isinstance(existing, list) else [existing]
        except Exception:
            queue = []
    queue.append(payload)
    cmd_file.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")


@mcp.tool()
def get_today_focus_summary() -> dict:
    """Lấy thống kê tập trung hôm nay: số phiên Pomodoro, số phút Deep Work, các task đang chờ và ý tưởng trong Parking Lot."""
    return db.get_today_analytics()


@mcp.tool()
def create_or_schedule_task(title: str, estimated_pomodoros: int = 1, category: str = "deep_work") -> str:
    """
    Tạo một công việc mới hoặc cất ý tưởng gây xao nhãng vào Parking Lot của Ted.
    category nhận một trong các giá trị: 'deep_work', 'shallow_work', 'parked_idea'.
    """
    task = db.add_task(title=title, category=category, estimated_pomodoros=estimated_pomodoros)
    _enqueue_ui_command({"type": "refresh_tasks", "task_id": task.id, "title": task.title})
    return (
        f"Đã thêm '{task.title}' (phân loại: {task.category}, dự kiến {task.estimated_pomodoros} Pomodoros) "
        f"vào danh sách của Ted."
    )


@mcp.tool()
def control_pomodoro(action: str, task_title: str = "Phiên Deep Work", duration_minutes: int = 25) -> str:
    """
    Điều khiển đồng hồ Pomodoro trên màn hình của Ted.
    action nhận: 'start', 'pause', 'resume', hoặc 'stop'.
    """
    _enqueue_ui_command(
        {
            "type": "control_pomodoro",
            "action": action.lower().strip(),
            "task_title": task_title,
            "duration_minutes": duration_minutes,
        }
    )
    return f"Đã gửi lệnh '{action}' phiên Pomodoro '{task_title}' ({duration_minutes} phút) tới giao diện Ted."


@mcp.tool()
def change_character_skin(skin: str = DEFAULT_CHARACTER_SKIN) -> str:
    """
    Đổi hình dáng nhân vật đồng hành trên màn hình Desktop của người dùng.
    skin là id nhân vật. Mặc định có 6 giá trị: 'cat' (Mèo), 'owl' (Cú đêm), 'panda' (Gấu trúc), 'shiba' (Cún Shiba),
    'bunny' (Thỏ bông), 'penguin' (Cánh cụt); bản build cài Character Pack dùng id nhân vật của pack (id sai → trả danh sách hợp lệ).
    """
    skin_key = skin.lower().strip()
    if skin_key not in CHARACTER_SKINS:
        allowed = ", ".join(CHARACTER_SKINS.keys())
        return f"Nhân vật '{skin}' không hợp lệ. Vui lòng chọn một trong các nhân vật: {allowed}."
    _enqueue_ui_command({"type": "change_character", "skin": skin_key})
    # MCP không đọc được trạng thái mở khoá (DB nằm ở tiến trình app): chỉ báo đã gửi yêu cầu, không khẳng định đã đổi
    return (f"Đã gửi yêu cầu đổi nhân vật sang {CHARACTER_SKINS[skin_key]}; "
            "nhân vật đang bị khóa sẽ bị ứng dụng từ chối.")


@mcp.tool()
def nudge_user(message: str, mood: str = "GENTLE_NUDGE") -> str:
    """
    Hiển thị lời nhắc nhẹ nhàng và thay đổi biểu cảm của nhân vật Ted trên màn hình.
    mood nhận: 'IDLE', 'FOCUS', 'GENTLE_NUDGE', 'CHEER', hoặc 'REST'.
    """
    _enqueue_ui_command({"type": "nudge_user", "mood": mood, "message": message})
    return f"Ted đã hiển thị lời nhắc với biểu cảm [{mood}]: {message}"


@mcp.tool()
def save_daily_journal(date: str, ai_summary: str, mood_tag: str = "productive") -> str:
    """Lưu bản tổng kết Daily Journal cuối ngày vào cơ sở dữ liệu SQLite của Ted."""
    journal = db.update_journal(target_date=date, ai_summary=ai_summary, mood_tag=mood_tag)
    _enqueue_ui_command({"type": "refresh_tasks"})
    return f"Đã lưu bản tổng kết Daily Journal ngày {journal.date} (tâm trạng: {journal.mood_tag})."


@mcp.tool()
def move_task_to_rock(task_id: str) -> str:
    """Chuyển 1 công việc TODO sang Rocks (vướng mắc tồn đọng / việc lớn khó)."""
    rock = db.move_task_to_rock(task_id)
    if not rock:
        return f"Không tìm thấy công việc với id: {task_id}"
    _enqueue_ui_command({"type": "refresh_tasks"})
    return f"Đã chuyển công việc '{rock.title}' sang danh sách Rocks."


@mcp.tool()
def move_rock_to_task(rock_id: str) -> str:
    """Chuyển 1 Rock sang danh sách công việc TODO cần làm."""
    task = db.move_rock_to_task(rock_id)
    if not task:
        return f"Không tìm thấy Rock với id: {rock_id}"
    _enqueue_ui_command({"type": "refresh_tasks", "task_id": task.id, "title": task.title})
    return f"Đã chuyển Rock '{task.title}' thành công việc Todo Deep Work."


def run_mcp_server():
    mcp.run()


if __name__ == "__main__":
    run_mcp_server()
