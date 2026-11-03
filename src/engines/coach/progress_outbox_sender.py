"""Gửi báo cáo tiến độ theo ngày: đóng băng payload các ngày đã qua, gửi cũ → mới, lỗi thì dừng (trừ khi đã bỏ hẳn)."""

import json
import logging
from datetime import timedelta
from typing import Callable

from src.bridge.hermes_offline_probe_and_backoff import OfflineBackoff, OfflineProbe
from src.bridge.hermes_json_contract_request import request_json
from src.engines.coach.coach_module_services import CoachModuleServices
from src.engines.coach.coach_quiz_writing_report_schemas import ProgressReportSavedReply
from src.engines.coach.coach_request_envelope import envelope
from src.engines.coach.coach_stats_collector import collect_progress_payload

logger = logging.getLogger("ted")

BACKFILL_DAYS = 7
FAILED_PERMANENTLY = "failed_permanently"


class ProgressOutboxSender:
    def __init__(self, services: CoachModuleServices, request_sync: Callable[[], None]):
        self._s = services
        self._request_sync = request_sync   # hook Phase 08: báo cáo đã lưu → kéo kế hoạch mới
        self._backoff = OfflineBackoff()

    def enqueue_missing(self) -> int:
        """Ngày đã qua (≤7 ngày lùi, không gồm hôm nay) có lượt trả lời mà chưa có dòng outbox → đóng băng payload."""
        learner, now, added = self._s.learner_id, self._s.now(), 0
        if not learner:
            return 0
        for back in range(1, BACKFILL_DAYS + 1):
            day = now.date() - timedelta(days=back)
            if self._s.outbox.get(self._s.module_id, day.isoformat()) is not None:
                continue
            payload = collect_progress_payload(self._s.attempts, self._s.module_id, learner, day, now, self._s.tz)
            if payload is not None and self._s.outbox.upsert_report(self._s.module_id, day.isoformat(), payload, now):
                added += 1
        return added

    async def flush(self) -> int:
        """Gửi các dòng pending cũ trước. Lỗi: attempts+1; còn pending → dừng (không dồn spam);
        chạm max_attempts → failed_permanently và đi tiếp ngày sau (Red Team #7). Trả số báo cáo đã gửi."""
        client, sent = self._s.client(), 0
        if client is None or self._backoff.blocked(self._s.now()):
            return 0
        for row in self._s.outbox.pending_reports(self._s.module_id):
            probe = OfflineProbe(client)
            try:
                reply = await request_json(
                    probe, envelope("TED_PROGRESS_REPORT", json.loads(row.payload_json)), ProgressReportSavedReply)
            except Exception:
                logger.exception("Gửi báo cáo %s lỗi bất ngờ", row.date)
                reply = None
            if reply is not None and reply.saved:
                self._s.outbox.mark_sent(self._s.module_id, row.date, self._s.now())
                sent += 1
                self._backoff.reset()
                continue
            if probe.offline:   # mất mạng KHÔNG tốn lượt thử (tránh failed_permanently = mất dữ liệu); lùi lịch rồi dừng
                self._backoff.on_offline(self._s.now())
                break
            error = "không có phản hồi" if reply is None else (reply.error or "saved=false")
            status = self._s.outbox.mark_failed(self._s.module_id, row.date, error, self._s.now())
            if status != FAILED_PERMANENTLY:
                break
        if sent:
            self._request_sync()
        return sent

    async def run_cycle(self) -> int:
        self.enqueue_missing()
        return await self.flush()

