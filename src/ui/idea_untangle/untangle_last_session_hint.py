"""Dòng "Lần trước": tóm tắt phản biện của phiên Gỡ Rối gần nhất gắn với task (rỗng nếu chưa có)."""

import json
from datetime import timezone
from typing import Optional

from src.core.i18n import tr


def last_session_hint(repo, task_id: Optional[str]) -> str:
    if not task_id:
        return ""
    for row in repo.recent_for_task(task_id, limit=1):
        try:
            summary = str((json.loads(row.critique_json or "{}") or {}).get("summary", ""))[:200]
        except (ValueError, AttributeError):
            summary = ""
        if summary:
            started = row.started_at if row.started_at.tzinfo else row.started_at.replace(tzinfo=timezone.utc)
            return tr("untangle_last_time", when=started.astimezone().strftime("%d/%m %H:%M"), summary=summary)
    return ""
