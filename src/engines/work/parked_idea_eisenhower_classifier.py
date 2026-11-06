"""Task/ý tưởng mới (Dashboard, Bãi đỗ, Hermes/MCP) → Hermes gợi ý ô Eisenhower ở nền; chỉ ghi nếu task còn "Unsorted" (người dùng đã kéo thì giữ nguyên)."""

import logging
from datetime import date, datetime
from typing import Optional

from sqlmodel import Session, select

from src.bridge.openai_json_contract_request import request_openai_json_contract as request_json
from src.core.background_task_spawner import spawn_background_task
from src.core.i18n import tr
from src.core.models import DatabaseManager, Task
from src.engines.work.daily_briefing_builder import sanitize_untrusted_text
from src.engines.work.eisenhower_contract_schemas import EisenhowerClassification
from src.modules_runtime.prompt_template_renderer import load_prompt

logger = logging.getLogger("ted")

MAX_IDEA_CHARS = 200
CLASSIFY_TIMEOUT_SECS = 30.0
ACK_BUBBLE_MS = 6_000
QUADRANT_LABELS = {1: "Làm ngay", 2: "Lên lịch", 3: "Giao việc", 4: "Loại bỏ"}


class ParkedIdeaClassifier:
    def __init__(self, manifest, ctx, db_engine):
        self._manifest = manifest
        self._ctx = ctx
        self._db_engine = db_engine
        self._tasks = DatabaseManager.for_engine(db_engine)

    def on_task_added(self, task_id: str, title: str) -> None:
        """Slot của FocusEngine.task_added: không có event loop (test đồng bộ) thì bỏ qua.
        Chụp updated_at ngay lúc đỗ: sau đó người dùng chạm vào task (kéo thả, kể cả về Unsorted) thì giữ nguyên."""
        coro = self.classify(task_id, title, parked_updated_at=self._updated_at(task_id))
        try:
            spawn_background_task(coro, "work-eisenhower-classify")
        except RuntimeError:
            coro.close()

    def _category(self, task_id: str) -> Optional[str]:
        with Session(self._db_engine) as session:
            task = session.get(Task, task_id)
            return task.category if task is not None else None

    def _updated_at(self, task_id: str) -> Optional[datetime]:
        with Session(self._db_engine) as session:
            task = session.get(Task, task_id)
            return task.updated_at if task is not None else None

    async def classify(self, task_id: str, title: str, parked_updated_at: Optional[datetime] = None) -> bool:
        """True nếu đã ghi ô mới. Offline/lỗi → im lặng, task vẫn Unsorted. parked_updated_at None → chỉ kiểm tra còn Unsorted."""
        pool = self._ctx.client_pool
        client = pool.for_module(self._manifest.id) if pool else None
        idea = sanitize_untrusted_text(title or "", MAX_IDEA_CHARS)
        if client is None or not idea:
            return False
        prompt = load_prompt(self._manifest, "eisenhower_classify", {"today": date.today().isoformat(), "idea": idea})
        if not prompt:
            return False
        try:
            result = await request_json(client, prompt, EisenhowerClassification, timeout=CLASSIFY_TIMEOUT_SECS)
        except Exception:
            logger.exception("Phân loại ý tưởng lỗi")
            return False
        if result is None or not self._assign_if_untouched(task_id, result.quadrant, parked_updated_at):
            return False
        self._notify(task_id, result.quadrant)
        return True

    def _assign_if_untouched(self, task_id: str, quadrant: int, parked_updated_at: Optional[datetime]) -> bool:
        # Kiểm tra + ghi liền nhau, không await giữa chừng → không đè lên lần kéo thả của người dùng
        with Session(self._db_engine) as session:
            task = session.get(Task, task_id)
            if task is None or task.quadrant is not None:
                return False
            if parked_updated_at is not None and task.updated_at != parked_updated_at:
                return False  # người dùng đã chạm vào task (vd. kéo về Unsorted) → coi là lựa chọn có chủ đích
            orders = session.exec(select(Task.matrix_order).where(Task.quadrant == quadrant)).all()
        end_of_quadrant = max(orders, default=-1.0) + 1.0  # cuối ô đích, không hoà với đầu cột
        return self._tasks.set_task_quadrant(task_id, quadrant, order=end_of_quadrant) is not None

    def _notify(self, task_id: str, quadrant: int) -> None:
        focus = self._ctx.focus_engine
        if focus is not None:
            focus.tasks_updated.emit()  # UI (ma trận / danh sách) tự refresh
        bubble = self._ctx.bubble
        if bubble is not None and not bubble.is_busy():
            text = f"Em xếp vào Q{quadrant} – {QUADRANT_LABELS[quadrant]} nhé"
            dashboard = getattr(self._ctx, "dashboard", None)
            label = tr("bubble_btn_view_parking" if self._category(task_id) == "parked_idea" else "bubble_btn_view_tasks")
            actions = [(label, lambda: dashboard.open_tasks_list(task_id))] if dashboard else []
            bubble.show_message(text, mood="CHEER", actions=actions, timeout_ms=ACK_BUBBLE_MS)
