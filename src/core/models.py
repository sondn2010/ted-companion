import logging
from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import uuid4
from sqlalchemy import event
from sqlmodel import Field, Session, SQLModel, create_engine, select
from src.config import settings

logger = logging.getLogger("ted")


class Task(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str
    category: str = Field(default="deep_work")  # deep_work, shallow_work, parked_idea
    estimated_pomodoros: int = Field(default=1)
    completed_pomodoros: int = Field(default=0)
    status: str = Field(default="todo")         # todo, in_progress, done, archived
    scheduled_date: str = Field(default_factory=lambda: date.today().isoformat())
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    synced_to_hermes: bool = Field(default=False)
    quadrant: Optional[int] = Field(default=None)  # None = chưa phân loại, 1..4 = Eisenhower Q1..Q4
    matrix_order: float = Field(default=0.0)       # thứ tự trong 1 cột (float để chèn giữa không cần đánh số lại)
    notes: str = Field(default="")                 # ghi chú tự do (Gỡ Rối Ý Tưởng nối thêm vào đây)


# Cột thêm sau này: DDL dùng để nâng cấp DB cũ tại chỗ (xem sqlite_add_missing_columns_migration)
TASK_ADDED_COLUMNS = {"quadrant": "INTEGER", "matrix_order": "FLOAT NOT NULL DEFAULT 0.0", "notes": "TEXT NOT NULL DEFAULT ''"}
TASK_NOTES_MAX_CHARS = 8000  # quá giới hạn → bỏ phần đầu (cũ nhất)
# Task mẫu tạo khi DB rỗng; máy thứ 2 bật đồng bộ sẽ xoá bản chưa đụng tới để không nhân đôi
WELCOME_TASK_TITLES = ("Khởi động phiên Deep Work đầu tiên cùng Ted", "Kết nối thử nghiệm với Não AI (Local / VPS)")


class FocusSession(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    task_id: Optional[str] = Field(default=None, foreign_key="task.id")
    intent_statement: str = Field(default="Tập trung hoàn thành công việc")
    planned_minutes: int = Field(default=25)
    actual_minutes: int = Field(default=0)
    distraction_count: int = Field(default=0)
    focus_rating: Optional[int] = Field(default=None)  # 1 - 5
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = Field(default=None)
    synced_to_hermes: bool = Field(default=False)


class DailyJournal(SQLModel, table=True):
    date: str = Field(default_factory=lambda: date.today().isoformat(), primary_key=True)
    morning_intention: Optional[str] = None
    evening_reflection: Optional[str] = None
    ai_summary: Optional[str] = None
    mood_tag: Optional[str] = Field(default="productive")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Đăng ký toàn bộ bảng của các phase sau vào metadata trước khi DatabaseManager gọi create_all
import src.core.register_all_table_models  # noqa: E402,F401
from src.core.sqlite_add_missing_columns_migration import ensure_columns  # noqa: E402


def _configure_sqlite_connection(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=5000;")  # khớp connect timeout 5s (DB chạy trên luồng GUI, đừng treo pet lâu)
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.close()


def _local_date_iso(moment: datetime) -> str:
    """started_at lưu UTC (SQLite trả về naive) → đổi sang ngày theo giờ máy, khớp date.today()."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().date().isoformat()


def _validate_quadrant(quadrant: Optional[int]) -> None:
    if quadrant is not None and (isinstance(quadrant, bool) or quadrant not in (1, 2, 3, 4)):
        raise ValueError(f"quadrant phải là None hoặc 1..4, nhận được {quadrant!r}")


class DatabaseManager:
    """Lớp truy xuất cơ sở dữ liệu SQLite Local-First tại ~/.ted/ted_local.db."""

    def __init__(self):
        sqlite_url = f"sqlite:///{settings.db_path}"
        # timeout + WAL để coroutine nền và QTimer ghi đồng thời không bị "database is locked"
        self.engine = create_engine(sqlite_url, connect_args={"check_same_thread": False, "timeout": 5.0})
        event.listen(self.engine, "connect", _configure_sqlite_connection)
        SQLModel.metadata.create_all(self.engine)
        try:
            ensure_columns(self.engine, "task", TASK_ADDED_COLUMNS)  # DB cũ chưa có cột quadrant/matrix_order
        except Exception:  # vd. DB đang bị instance khác khoá: app vẫn khởi động, nâng cấp cột thử lại lần mở sau
            logger.exception("Nâng cấp cột bảng task thất bại, bỏ qua và tiếp tục khởi động")
        self._seed_welcome_tasks_if_empty()

    @classmethod
    def for_engine(cls, engine) -> "DatabaseManager":
        """Facade truy vấn trên engine có sẵn (engine của module / test), không tạo file DB mới, không seed."""
        manager = cls.__new__(cls)
        manager.engine = engine
        return manager

    def _seed_welcome_tasks_if_empty(self):
        with Session(self.engine) as session:
            existing = session.exec(select(Task)).first()
            if not existing:
                today_str = date.today().isoformat()
                t1 = Task(
                    title=WELCOME_TASK_TITLES[0],
                    category="deep_work",
                    estimated_pomodoros=1,
                    scheduled_date=today_str,
                )
                t2 = Task(
                    title=WELCOME_TASK_TITLES[1],
                    category="deep_work",
                    estimated_pomodoros=2,
                    scheduled_date=today_str,
                )
                session.add(t1)
                session.add(t2)
                session.commit()

    def list_tasks(self, include_done: bool = True) -> List[Task]:
        with Session(self.engine) as session:
            stmt = select(Task).order_by(Task.updated_at.desc())
            tasks = list(session.exec(stmt).all())
            if not include_done:
                tasks = [t for t in tasks if t.status != "done"]
            return tasks

    def get_task(self, task_id: str) -> Optional[Task]:
        with Session(self.engine) as session:
            return session.get(Task, task_id)

    def update_task(
        self,
        task_id: str,
        title: str,
        category: str,
        estimated_pomodoros: int,
        quadrant: Optional[int],
        status: str,
        scheduled_date: str,
        notes: Optional[str] = None,
    ) -> Optional[Task]:
        """Sửa thông tin task (form Chi tiết công việc). Đổi ô Eisenhower → xếp cuối ô mới. Trả None nếu không có task.

        notes=None → giữ nguyên ghi chú cũ."""
        _validate_quadrant(quadrant)
        title = title.strip()
        if not title:
            raise ValueError("Tên công việc không được để trống")
        with Session(self.engine) as session:
            task = session.get(Task, task_id)
            if task is None:
                return None
            if task.quadrant != quadrant:
                orders = session.exec(select(Task.matrix_order).where(Task.quadrant == quadrant, Task.id != task_id)).all()
                task.matrix_order = (max(orders) + 1.0) if orders else 0.0
            task.title = title
            task.category = category
            task.estimated_pomodoros = max(1, estimated_pomodoros)
            task.quadrant = quadrant
            task.status = status
            task.scheduled_date = scheduled_date
            if notes is not None:
                task.notes = notes[-TASK_NOTES_MAX_CHARS:]
            task.updated_at = datetime.now(timezone.utc)
            task.synced_to_hermes = False
            session.add(task)
            session.commit()
            session.refresh(task)
            return task

    def append_task_notes(self, task_id: str, text: str) -> Optional[Task]:
        """Nối 1 mục ghi chú 🧶 (kèm ngày giờ máy) vào cuối notes; cắt đầu nếu >8000 ký tự. None nếu không có task."""
        text = text.strip()
        with Session(self.engine) as session:
            task = session.get(Task, task_id)
            if task is None:
                return None
            if text:
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                entry = f"\n\n— 🧶 {stamp}\n{text}"
                task.notes = f"{task.notes or ''}{entry}".lstrip("\n")[-TASK_NOTES_MAX_CHARS:]
                task.updated_at = datetime.now(timezone.utc)
                task.synced_to_hermes = False
                session.add(task)
                session.commit()
                session.refresh(task)
            return task

    def add_task(
        self,
        title: str,
        category: str = "deep_work",
        estimated_pomodoros: int = 1,
        quadrant: Optional[int] = None,
        notes: str = "",
    ) -> Task:
        _validate_quadrant(quadrant)
        with Session(self.engine) as session:
            task = Task(
                title=title.strip(),
                category=category,
                estimated_pomodoros=max(1, estimated_pomodoros),
                scheduled_date=date.today().isoformat(),
                quadrant=quadrant,
                notes=notes,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            return task

    def set_task_quadrant(
        self, task_id: str, quadrant: Optional[int], order: Optional[float] = None
    ) -> Optional[Task]:
        """Chuyển việc sang ô Eisenhower (None = chưa phân loại). Trả None nếu không có task."""
        _validate_quadrant(quadrant)
        with Session(self.engine) as session:
            task = session.get(Task, task_id)
            if task is None:
                return None
            task.quadrant = quadrant
            if order is not None:
                task.matrix_order = float(order)
            task.updated_at = datetime.now(timezone.utc)
            task.synced_to_hermes = False
            session.add(task)
            session.commit()
            session.refresh(task)
            return task

    def reorder_quadrant(self, quadrant: Optional[int], ordered_ids: List[str]) -> None:
        """Ghi matrix_order = chỉ số cho các task trong cột (gọi sau khi thả). Id lạ / sai cột bị bỏ qua."""
        _validate_quadrant(quadrant)
        with Session(self.engine) as session:
            for index, task_id in enumerate(ordered_ids):
                task = session.get(Task, task_id)
                if task is None or task.quadrant != quadrant:
                    continue
                task.matrix_order = float(index)
                task.updated_at = datetime.now(timezone.utc)
                task.synced_to_hermes = False
                session.add(task)
            session.commit()

    def next_important_tasks(self, limit: int = 3) -> List[Task]:
        """Việc mở (todo|in_progress) thuộc Q1 rồi Q2, theo matrix_order rồi updated_at; gồm cả ý tưởng đã đỗ."""
        with Session(self.engine) as session:
            stmt = (
                select(Task)
                .where(Task.status.in_(("todo", "in_progress")), Task.quadrant.in_((1, 2)))
                .order_by(Task.quadrant, Task.matrix_order, Task.updated_at)
                .limit(max(0, limit))
            )
            return list(session.exec(stmt).all())

    def mark_task_done(self, task_id: str) -> Optional[Task]:
        with Session(self.engine) as session:
            task = session.get(Task, task_id)
            if task:
                task.status = "done" if task.status != "done" else "todo"
                task.updated_at = datetime.now(timezone.utc)
                session.add(task)
                session.commit()
                session.refresh(task)
            return task

    def delete_task(self, task_id: str):
        self.delete_tasks([task_id])

    def delete_tasks(self, task_ids: List[str]) -> int:
        """Xoá nhiều task trong 1 giao dịch; id không tồn tại bị bỏ qua. Trả số task đã xoá."""
        deleted = 0
        with Session(self.engine) as session:
            for task_id in dict.fromkeys(task_ids):
                task = session.get(Task, task_id)
                if task:
                    session.delete(task)
                    deleted += 1
            session.commit()
        return deleted

    def move_task_to_rock(self, task_id: str):
        """Chuyển 1 Task sang Rock (vướng mắc tồn đọng / việc lớn khó) trong 1 giao dịch."""
        from src.engines.work.rock_model_and_repository import Rock
        with Session(self.engine) as session:
            task = session.get(Task, task_id)
            if task is None:
                return None
            rock = Rock(
                title=task.title.strip(),
                detail=task.notes or "",
                status="open",
            )
            session.add(rock)
            session.delete(task)
            session.commit()
            session.refresh(rock)
            return rock

    def move_rock_to_task(self, rock_id: str) -> Optional[Task]:
        """Chuyển 1 Rock sang Task (Deep Work cần làm) trong 1 giao dịch."""
        from src.engines.work.rock_model_and_repository import Rock
        with Session(self.engine) as session:
            rock = session.get(Rock, rock_id)
            if rock is None:
                return None
            notes = rock.detail or ""
            if rock.resolved_note:
                notes = f"{notes}\n{rock.resolved_note}".strip()
            task = Task(
                title=rock.title.strip() or "Công việc từ Rock",
                category="deep_work",
                estimated_pomodoros=1,
                status="todo",
                scheduled_date=date.today().isoformat(),
                notes=notes,
            )
            session.add(task)
            session.delete(rock)
            session.commit()
            session.refresh(task)
            return task

    def increment_task_pomodoro(self, task_id: Optional[str]):
        if not task_id:
            return
        with Session(self.engine) as session:
            task = session.get(Task, task_id)
            if task:
                task.completed_pomodoros += 1
                task.updated_at = datetime.now(timezone.utc)
                session.add(task)
                session.commit()

    def create_focus_session(self, intent: str, planned_minutes: int, task_id: Optional[str] = None) -> FocusSession:
        with Session(self.engine) as session:
            fs = FocusSession(
                task_id=task_id,
                intent_statement=intent,
                planned_minutes=planned_minutes,
            )
            session.add(fs)
            session.commit()
            session.refresh(fs)
            return fs

    def finish_focus_session(
        self,
        session_id: str,
        actual_minutes: int,
        distraction_count: int,
        focus_rating: int = 5,
    ) -> Optional[FocusSession]:
        with Session(self.engine) as session:
            fs = session.get(FocusSession, session_id)
            if fs:
                fs.actual_minutes = actual_minutes
                fs.distraction_count = distraction_count
                fs.focus_rating = focus_rating
                fs.ended_at = datetime.now(timezone.utc)
                session.add(fs)
                session.commit()
                session.refresh(fs)
            return fs

    def get_today_analytics(self) -> dict:
        today_str = date.today().isoformat()
        with Session(self.engine) as session:
            all_sessions = list(session.exec(select(FocusSession)).all())
            today_sessions = [
                s for s in all_sessions if _local_date_iso(s.started_at) == today_str and s.actual_minutes > 0
            ]
            all_tasks = list(session.exec(select(Task)).all())
            pending_deep = [t.title for t in all_tasks if t.status != "done" and t.category != "parked_idea"]
            parked_ideas = [t.title for t in all_tasks if t.status != "done" and t.category == "parked_idea"]
            done_tasks = [t.title for t in all_tasks if t.status == "done" and t.scheduled_date == today_str]

            total_mins = sum(s.actual_minutes for s in today_sessions)
            total_distractions = sum(s.distraction_count for s in today_sessions)
            ratings = [s.focus_rating for s in today_sessions if s.focus_rating is not None]
            avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 5.0

            return {
                "date": today_str,
                "completed_sessions": len(today_sessions),
                "total_focus_minutes": total_mins,
                "total_distractions": total_distractions,
                "average_focus_rating": avg_rating,
                "completed_tasks": done_tasks,
                "pending_tasks": pending_deep,
                "parked_ideas": parked_ideas,
            }

    def get_or_create_journal(self, target_date: Optional[str] = None) -> DailyJournal:
        d_str = target_date or date.today().isoformat()
        with Session(self.engine) as session:
            journal = session.get(DailyJournal, d_str)
            if not journal:
                journal = DailyJournal(date=d_str)
                session.add(journal)
                session.commit()
                session.refresh(journal)
            return journal

    def update_journal(
        self,
        target_date: Optional[str] = None,
        morning_intention: Optional[str] = None,
        evening_reflection: Optional[str] = None,
        ai_summary: Optional[str] = None,
        mood_tag: Optional[str] = None,
    ) -> DailyJournal:
        d_str = target_date or date.today().isoformat()
        with Session(self.engine) as session:
            journal = session.get(DailyJournal, d_str)
            if not journal:
                journal = DailyJournal(date=d_str)
            if morning_intention is not None:
                journal.morning_intention = morning_intention
            if evening_reflection is not None:
                journal.evening_reflection = evening_reflection
            if ai_summary is not None:
                journal.ai_summary = ai_summary
            if mood_tag is not None:
                journal.mood_tag = mood_tag
            journal.updated_at = datetime.now(timezone.utc)
            session.add(journal)
            session.commit()
            session.refresh(journal)
            return journal

    def get_unsynced_sessions(self) -> List[FocusSession]:
        with Session(self.engine) as session:
            stmt = select(FocusSession).where(
                FocusSession.synced_to_hermes == False,  # noqa: E712
                FocusSession.ended_at != None,           # noqa: E711
            )
            return list(session.exec(stmt).all())

    def mark_session_synced(self, session_id: str):
        with Session(self.engine) as session:
            fs = session.get(FocusSession, session_id)
            if fs:
                fs.synced_to_hermes = True
                session.add(fs)
                session.commit()


db = DatabaseManager()
