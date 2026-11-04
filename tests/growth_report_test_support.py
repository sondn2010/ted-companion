"""Dụng cụ test báo cáo tăng trưởng: dữ liệu mẫu trên SQLite in-memory, registry/pool giả."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from src.core.gamification.badge_unlock_repository import BadgeUnlockRepository
from src.core.gamification.growth_report_aggregation import GrowthSources
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.xp_ledger_repository import XpLedgerRepository

TODAY = date(2026, 10, 22)   # thứ Năm; tuần trước bắt đầu 2026-10-12
SECRET_TITLE = "Báo cáo mật của khách hàng"   # không bao giờ được xuất hiện trong payload


def local_noon(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, 0).astimezone().astimezone(timezone.utc)


def make_sources(engine) -> GrowthSources:
    return GrowthSources(engine, XpLedgerRepository(engine), WellbeingDailyRepository(engine),
                         BadgeUnlockRepository(engine))


def seed_work_day(src: GrowthSources, day: date) -> None:
    src.ledger.add(f"task_done:t{day}:1", local_noon(day), "work", "work", "task_done",
                   {"title": SECRET_TITLE})
    src.wellbeing.add_minutes(day, 100)
    src.wellbeing.add_away(day, 30)


def seed_study_day(src: GrowthSources, day: date, module: str = "thcs") -> None:
    for i in range(3):
        src.ledger.add(f"qa:{module}:{day}:{i}", local_noon(day), module, "coach", "quiz_answered")
    src.ledger.add(f"qc:{module}:{day}:0", local_noon(day), module, "coach", "quiz_correct")


def fake_registry(*modules):
    """modules: (id, engine, learner_id)."""
    return SimpleNamespace(enabled=lambda: [SimpleNamespace(id=m, engine=e, learner_id=lid) for m, e, lid in modules])


class FakePool:
    def __init__(self, conn_of: dict, clients: dict):
        self._conn_of, self._clients = conn_of, clients

    def connection_id_for_module(self, module_id):
        return self._conn_of.get(module_id)

    def get(self, conn_id):
        return self._clients.get(conn_id)
