"""Outbox báo cáo tiến độ: mỗi (module, ngày) một dòng; không bao giờ ghi đè bản đã gửi; lỗi 1 ngày không chặn ngày khác."""

import json
import re
from datetime import date, datetime
from typing import Any, Optional

from sqlmodel import col, select

from src.engines.coach.coach_data_models import DATE_PATTERN, ProgressReportOutbox, open_session
from src.engines.coach.utc_aware_datetime_type import require_aware

_DATE_RE = re.compile(DATE_PATTERN, re.ASCII)


def validate_report_date(value: str) -> str:
    """Ngày đi vào tên file trên server → chỉ nhận đúng YYYY-MM-DD là ngày lịch có thật (Red Team #4)."""
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise ValueError(f"Ngày báo cáo không hợp lệ: {value!r}")
    date.fromisoformat(value)   # ValueError nếu như 2026-13-45
    return value


class ProgressReportOutboxRepository:
    def __init__(self, engine):
        self.engine = engine

    def upsert_report(self, module_id: str, report_date: str, payload: dict[str, Any], now: datetime) -> bool:
        """Tạo/cập nhật payload của ngày (gửi lại cùng ngày cho cùng kết quả). Đã sent=True → giữ nguyên, trả False."""
        validate_report_date(report_date)
        require_aware(now)
        body = json.dumps(payload, ensure_ascii=False)
        with open_session(self.engine) as session:
            row = session.get(ProgressReportOutbox, (module_id, report_date))
            if row is None:
                row = ProgressReportOutbox(module_id=module_id, date=report_date, payload_json=body, updated_at=now)
            elif row.sent:
                return False
            else:
                row.payload_json, row.status, row.attempts, row.last_error, row.updated_at = body, "pending", 0, "", now
            session.add(row)
            session.commit()
            return True

    def pending_reports(self, module_id: str) -> list[ProgressReportOutbox]:
        """Các ngày còn phải gửi, cũ trước. Dòng failed_permanently bị loại nên không chặn đầu hàng (Red Team #7)."""
        with open_session(self.engine) as session:
            stmt = select(ProgressReportOutbox).where(
                ProgressReportOutbox.module_id == module_id, ProgressReportOutbox.status == "pending",
            ).order_by(col(ProgressReportOutbox.date))
            return list(session.exec(stmt).all())

    def get(self, module_id: str, report_date: str) -> Optional[ProgressReportOutbox]:
        with open_session(self.engine) as session:
            return session.get(ProgressReportOutbox, (module_id, report_date))

    def mark_sent(self, module_id: str, report_date: str, now: datetime) -> None:
        with open_session(self.engine) as session:
            row = session.get(ProgressReportOutbox, (module_id, report_date))
            if row is None:
                return
            row.status, row.sent, row.last_error, row.updated_at = "sent", True, "", require_aware(now)
            session.add(row)
            session.commit()

    def mark_failed(self, module_id: str, report_date: str, error: str, now: datetime) -> str:
        """attempts+1; chạm max_attempts → failed_permanently. Trả về status mới ('' nếu không có dòng)."""
        with open_session(self.engine) as session:
            row = session.get(ProgressReportOutbox, (module_id, report_date))
            if row is None or row.sent:
                return ""
            row.attempts += 1
            row.last_error, row.updated_at = error[:300], require_aware(now)
            if row.attempts >= row.max_attempts:
                row.status = "failed_permanently"
            session.add(row)
            session.commit()
            return row.status
