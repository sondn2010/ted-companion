"""KV nhỏ lưu cờ runtime (ngày briefing cuối, snooze, nhắc đã bắn, ngày sync cuối...)."""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel


class AppStateKV(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KeyValueStore:
    def __init__(self, engine: Engine):
        self._engine = engine
        AppStateKV.__table__.create(engine, checkfirst=True)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with Session(self._engine) as session:
            row = session.get(AppStateKV, key)
            return row.value if row else default

    def set(self, key: str, value: str):
        with Session(self._engine) as session:
            row = session.get(AppStateKV, key)
            if row is None:
                row = AppStateKV(key=key, value=value)
            else:
                row.value = value
                row.updated_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()

    def get_json(self, key: str, default: Any = None) -> Any:
        raw = self.get(key)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default  # giá trị hỏng → coi như chưa có

    def set_json(self, key: str, value: Any):
        self.set(key, json.dumps(value, ensure_ascii=False))
