"""Gợi ý + khởi động phỏng vấn làm quen ([TED_ONBOARDING]) khi Hermes báo `needs_onboarding`."""

import logging

from src.engines.coach.coach_module_services import CoachModuleServices
from src.engines.coach.coach_request_envelope import envelope

logger = logging.getLogger("ted")
OFFER_TEXT = "Ted cần làm quen trước khi lên kế hoạch nhé 👋"
START_DISPLAY_TEXT = "Bắt đầu làm quen"
OFFER_TIMEOUT_MS = 60_000


class CoachOnboardingPrompt:
    def __init__(self, services: CoachModuleServices):
        self._s = services
        self._stopped = False

    def stop(self) -> None:
        """Module bị tắt: không mời / không mở chat nữa (kể cả nút trên bong bóng đã hiện)."""
        self._stopped = True

    def offer(self) -> None:
        """Bong bóng kèm nút [Bắt đầu]; bubble đang bận thì thôi — banner trong tab vẫn còn đó."""
        bubble = self._s.ctx.bubble
        if self._stopped or bubble is None or bubble.is_busy():
            return
        bubble.show_message(OFFER_TEXT, mood="CHEER", timeout_ms=OFFER_TIMEOUT_MS, actions=[("Bắt đầu", self.start)])

    def start(self) -> None:
        """Mở quick chat gắn với module, tự gửi gói [TED_ONBOARDING]; người dùng trả lời bình thường sau đó."""
        learner = self._s.learner_id
        quick_chat = self._s.ctx.quick_chat
        if self._stopped:
            return
        if not learner or quick_chat is None:
            logger.warning("Coach %s: không thể bắt đầu onboarding (thiếu learner_id hoặc quick chat)", self._s.module_id)
            return
        quick_chat.open_for(
            self._s.module_id, prefill=envelope("TED_ONBOARDING", {"learner": learner}), auto_send=True,
            display_text=START_DISPLAY_TEXT)
