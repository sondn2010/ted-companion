"""[TED_SYNC_PLAN]: dựng request → hỏi Hermes → áp snapshot/policy/overrides, hoặc chuyển sang onboarding.
Mỗi module_id tối đa 1 sync đang bay TOÀN TIẾN TRÌNH (kể cả engine cũ/mới khi bật-tắt module); gọi sync khi đang bận
→ ghi "yêu cầu chạy lại" và chạy thêm đúng 1 lần sau khi lần đang bay xong. Lỗi mạng/JSON → giữ nguyên snapshot cũ."""

import logging
from typing import Callable, Optional

from src.bridge.openai_json_contract_request import request_openai_json_contract as request_json
from src.engines.coach.coach_module_services import CoachModuleServices
from src.engines.coach.coach_request_envelope import envelope
from src.engines.coach.coach_stats_collector import collect_sync_stats
from src.engines.coach.coach_sync_plan_schemas import SyncPlanResponse

logger = logging.getLogger("ted")
SYNC_TIMEOUT_SECS = 60.0
FAILED_TEXT = "Chưa đồng bộ được, Ted dùng kế hoạch cũ nhé"
NO_CONNECTION_TEXT = "Chưa cấu hình kết nối Não AI cho module này — vào Cài đặt để chọn nhé"

# Kết quả của sync(): updated | needs_onboarding | failed | busy | skipped
UPDATED, NEEDS_ONBOARDING, FAILED, BUSY, SKIPPED = "updated", "needs_onboarding", "failed", "busy", "skipped"


# Đăng ký toàn tiến trình theo module_id: sync đang bay + yêu cầu chạy lại (service mới nhất, manual) (L2/M2)
_ACTIVE: set[str] = set()
_RERUN: dict[str, tuple["CoachSyncService", bool]] = {}


def last_sync_key(module_id: str) -> str:
    return f"coach.{module_id}.last_sync_date"


class CoachSyncService:
    def __init__(
        self, services: CoachModuleServices,
        busy_slots: Callable[[], Optional[list[dict]]] = lambda: None,
        on_needs_onboarding: Callable[[], None] = lambda: None,
        on_plan_applied: Callable[[], None] = lambda: None,
    ):
        self._s = services
        self._busy_slots = busy_slots
        self._on_needs_onboarding = on_needs_onboarding
        self._on_plan_applied = on_plan_applied   # vd. scheduler dựng lại timer vì interval có thể đổi
        self._stopped = False

    def stop(self) -> None:
        """Engine bị tắt: sync đang bay vẫn lưu dữ liệu nhưng không còn đụng UI (bong bóng / onboarding / timer)."""
        self._stopped = True
        if _RERUN.get(self._s.module_id, (None,))[0] is self:
            _RERUN.pop(self._s.module_id, None)

    def is_due_today(self) -> bool:
        """Chưa có sync thành công nào trong ngày địa phương hiện tại."""
        return self._s.ctx.kv.get(last_sync_key(self._s.module_id)) != self._s.today().isoformat()

    def build_request(self, learner: str, sent_done_ids: list[str]) -> dict:
        s, now = self._s, self._s.now()
        policy = s.policy()
        request = {
            "learner": learner,
            "now": now.isoformat(timespec="seconds"),
            "stats": collect_sync_stats(s.items, s.attempts, s.module_id, now, s.tz),
            "done_today": sent_done_ids,
            "current_policy": {
                "review_interval_mins": policy.review_interval_mins, "daily_cap": policy.daily_cap,
                "new_per_day": policy.new_per_day},
        }
        busy = self._busy_slots()
        if busy is not None:   # khoá chỉ có khi Ted lấy được lịch
            request["busy_slots"] = busy
        return request

    async def sync(self, manual: bool = False) -> str:
        module_id = self._s.module_id
        if module_id in _ACTIVE:
            _RERUN[module_id] = (self, manual)   # chạy lại 1 lần sau khi lần đang bay xong
            return BUSY
        _ACTIVE.add(module_id)
        try:
            result = await self._sync_once(manual)
        finally:
            _ACTIVE.discard(module_id)
        pending = _RERUN.pop(module_id, None)
        if pending is not None and not pending[0]._stopped:
            await pending[0].sync(pending[1])
        return result

    async def _sync_once(self, manual: bool) -> str:
        client, learner = self._s.client(), self._s.learner_id
        if client is None or not learner:   # không bao giờ gửi sang kết nối khác: giữ cache, chỉ nhắc cấu hình
            self._say(NO_CONNECTION_TEXT if client is None else FAILED_TEXT, manual, "GENTLE_NUDGE")
            return SKIPPED
        try:
            return await self._run(client, learner, manual)
        except Exception:
            logger.exception("Coach %s: sync lỗi bất ngờ", self._s.module_id)
            self._say(FAILED_TEXT, manual, "GENTLE_NUDGE")
            return FAILED

    async def _run(self, client, learner: str, manual: bool) -> str:
        s = self._s
        # Chốt các id đã tick TẠI THỜI ĐIỂM gửi: tick trong lúc request đang bay vẫn chưa được báo → sync sau mới gửi (Red Team #8)
        sent_done_ids = s.plans.unreported_done_ids(s.module_id)
        reply = await request_json(
            client, envelope("TED_SYNC_PLAN", self.build_request(learner, sent_done_ids)), SyncPlanResponse,
            timeout=SYNC_TIMEOUT_SECS)
        if reply is None:
            self._say(FAILED_TEXT, manual, "GENTLE_NUDGE")
            return FAILED
        s.ctx.kv.set(last_sync_key(s.module_id), s.today().isoformat())
        if reply.needs_onboarding or reply.payload is None:
            s.set_needs_onboarding(True)   # snapshot cũ KHÔNG bị ghi đè
            s.on_changed()
            if not self._stopped:
                self._on_needs_onboarding()
            return NEEDS_ONBOARDING
        payload = reply.payload
        s.plans.save_sync(s.module_id, payload, s.now(), reported_ids=sent_done_ids)
        s.items.apply_overrides(s.module_id, payload.srs_overrides, s.now())
        s.set_needs_onboarding(False)
        s.on_changed()
        if not self._stopped:
            self._on_plan_applied()
        self._say(f"Đã cập nhật kế hoạch: {len(payload.agenda)} việc hôm nay", manual, "CHEER")
        return UPDATED

    def _say(self, text: str, manual: bool, mood: str) -> None:
        bubble = self._s.ctx.bubble
        if manual and bubble is not None and not self._stopped:
            bubble.show_message(text, mood=mood, timeout_ms=8000)
