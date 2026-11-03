"""Menu cố định theo engine (nguồn duy nhất). Manifest không khai báo menu."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MenuAction:
    id: str
    label: str


ENGINE_MENUS: dict[str, list[MenuAction]] = {
    "work": [
        MenuAction("briefing", "📅 Công việc hôm nay"),
        MenuAction("tasks", "✅ Danh sách công việc"),
        MenuAction("ask", "❓ Hỏi Ted"),
        MenuAction("rocks", "🪨 Rocks"),
        MenuAction("calendar", "🗓️ Lịch họp"),
    ],
    "coach": [
        MenuAction("today", "📅 Hôm nay"),
        MenuAction("review_now", "🧠 Ôn ngay"),
        MenuAction("ask", "❓ Hỏi"),
        MenuAction("progress", "📈 Tiến độ & mốc"),
        MenuAction("sync", "🔄 Đồng bộ kế hoạch"),
    ],
}
