"""Xây dựng payload báo cáo hoạt động gửi về Não AI Hermes."""

from datetime import date
import json
from typing import Any, Dict, List
from src.core.activity_watcher.activity_table_models import DailyActivityRecord


def build_activity_report_dict(record: DailyActivityRecord) -> Dict[str, Any]:
    """Chuyển bản ghi SQLite thành dict cấu trúc chuẩn."""
    try:
        raw_apps = json.loads(record.top_apps_json or "{}")
    except Exception:
        raw_apps = {}

    # Chuyển đổi và sắp xếp top apps
    apps_list = []
    for app_name, secs in raw_apps.items():
        mins = round(secs / 60, 1)
        if mins > 0:
            apps_list.append({"app": app_name, "minutes": mins})
    apps_list.sort(key=lambda x: x["minutes"], reverse=True)

    study_mins = round(record.study_seconds / 60, 1)
    distraction_mins = round(record.distraction_seconds / 60, 1)
    neutral_mins = round(record.neutral_seconds / 60, 1)

    total_tracked = study_mins + distraction_mins
    focus_pct = round((study_mins / total_tracked) * 100, 1) if total_tracked > 0 else 100.0

    has_issue = bool(record.unsafe_attempts > 0 or record.breach_count > 0)

    return {
        "kind": "daily_activity",
        "date": record.date,
        "learner": record.learner,
        "study_minutes": study_mins,
        "distraction_minutes": distraction_mins,
        "neutral_minutes": neutral_mins,
        "focus_percentage": focus_pct,
        "self_corrected_count": record.self_corrected_count,
        "breach_count": record.breach_count,
        "unsafe_attempts": record.unsafe_attempts,
        "status": "warning" if has_issue else "good",
        "top_apps": apps_list[:8],
    }


def format_ted_activity_report_message(payload: Dict[str, Any]) -> str:
    """Định dạng bản tin theo giao thức [TED_ACTIVITY_REPORT] cho Hermes."""
    return f"[TED_ACTIVITY_REPORT]\n<json>{json.dumps(payload, ensure_ascii=False)}</json>"
