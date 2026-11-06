"""DB của bản cũ (3 bảng + dữ liệu) nâng cấp bằng create_all: dòng cũ nguyên vẹn, bảng mới xuất hiện."""
import sqlite3

from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine, select

OLD_SCHEMA = """
CREATE TABLE task (id VARCHAR PRIMARY KEY, title VARCHAR NOT NULL, category VARCHAR NOT NULL,
    estimated_pomodoros INTEGER NOT NULL, completed_pomodoros INTEGER NOT NULL, status VARCHAR NOT NULL,
    scheduled_date VARCHAR NOT NULL, updated_at DATETIME NOT NULL, synced_to_hermes BOOLEAN NOT NULL);
CREATE TABLE dailyjournal (date VARCHAR PRIMARY KEY, morning_intention VARCHAR, evening_reflection VARCHAR,
    ai_summary VARCHAR, mood_tag VARCHAR, updated_at DATETIME NOT NULL);
CREATE TABLE focussession (id VARCHAR PRIMARY KEY, task_id VARCHAR, intent_statement VARCHAR NOT NULL,
    planned_minutes INTEGER NOT NULL, actual_minutes INTEGER NOT NULL, distraction_count INTEGER NOT NULL,
    focus_rating INTEGER, started_at DATETIME NOT NULL, ended_at DATETIME, synced_to_hermes BOOLEAN NOT NULL);
INSERT INTO task VALUES ('t1','Việc cũ','deep_work',2,1,'todo','2026-10-01','2026-10-01 00:00:00',0);
INSERT INTO dailyjournal VALUES ('2026-10-01','ý định',NULL,NULL,'productive','2026-10-01 00:00:00');
"""


def test_create_all_over_old_database_preserves_rows_and_adds_new_tables(tmp_path):
    db = tmp_path / "ted_local.db"
    con = sqlite3.connect(db)
    con.executescript(OLD_SCHEMA)
    con.commit()
    con.close()

    from src.core.models import TASK_ADDED_COLUMNS, DailyJournal, Task
    from src.core.sqlite_add_missing_columns_migration import ensure_columns
    engine = create_engine(f"sqlite:///{db}")
    SQLModel.metadata.create_all(engine)
    ensure_columns(engine, "task", TASK_ADDED_COLUMNS)  # y như DatabaseManager.__init__
    with Session(engine) as session:
        task = session.exec(select(Task)).one()
        assert (task.id, task.title, task.completed_pomodoros) == ("t1", "Việc cũ", 1)
        assert (task.quadrant, task.matrix_order) == (None, 0.0)
        assert session.exec(select(DailyJournal)).one().morning_intention == "ý định"
    names = set(inspect(engine).get_table_names())
    assert {"quizitem", "rock", "calendareventcache", "plansnapshot", "appstatekv"} <= names
    engine.dispose()
