"""RockRepository: CRUD, lọc đã đóng, stale theo ngày, bền vững qua lần mở lại DB."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, create_engine

from src.engines.work.rock_model_and_repository import Rock, RockRepository, rock_age_days


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rocks.db'}")
    yield RockRepository(engine)
    engine.dispose()


def _backdate(repo: RockRepository, rock_id: str, days: int):
    with Session(repo._engine) as s:
        rock = s.get(Rock, rock_id)
        rock.created_at = datetime.now(timezone.utc) - timedelta(days=days)
        s.add(rock)
        s.commit()


def test_add_strips_and_rejects_blank_title(repo):
    rock = repo.add("  Chờ duyệt ngân sách ", " chi tiết ")
    assert (rock.title, rock.detail, rock.status) == ("Chờ duyệt ngân sách", "chi tiết", "open")
    with pytest.raises(ValueError):
        repo.add("   ")


def test_resolve_and_drop_set_status_note_and_filter_lists(repo):
    a, b, c = repo.add("A"), repo.add("B"), repo.add("C")
    assert repo.set_status(a.id, "resolved", " xong nhờ anh Nam ").resolved_note == "xong nhờ anh Nam"
    assert repo.set_status(b.id, "dropped").status == "dropped"
    assert [r.title for r in repo.list()] == ["C"]
    assert {r.title for r in repo.list(include_closed=True)} == {"A", "B", "C"}
    assert repo.set_status("khong-ton-tai", "resolved") is None
    with pytest.raises(ValueError):
        repo.set_status(c.id, "bogus")


def test_stale_uses_age_greater_than_min_days_oldest_first_and_skips_closed(repo):
    old, older, fresh, closed = repo.add("old"), repo.add("older"), repo.add("fresh"), repo.add("closed")
    _backdate(repo, old.id, 5)
    _backdate(repo, older.id, 9)
    _backdate(repo, fresh.id, 3)  # đúng 3 ngày → chưa quá hạn (age > 3)
    _backdate(repo, closed.id, 20)
    repo.set_status(closed.id, "dropped")
    stale = repo.stale(datetime.now(timezone.utc), 3)
    assert [r.title for r in stale] == ["older", "old"]
    assert [rock_age_days(r) for r in stale] == [9, 5]


def test_rocks_persist_across_reopen(tmp_path):
    url = f"sqlite:///{tmp_path / 'persist.db'}"
    first = create_engine(url)
    RockRepository(first).add("Còn đó sau khi khởi động lại")
    first.dispose()
    second = create_engine(url)
    assert [r.title for r in RockRepository(second).list()] == ["Còn đó sau khi khởi động lại"]
    second.dispose()


def test_get_and_delete_rock(repo):
    rock = repo.add("Việc khó cần tách", "chi tiết rock")
    fetched = repo.get(rock.id)
    assert fetched is not None
    assert fetched.title == "Việc khó cần tách"
    assert fetched.detail == "chi tiết rock"

    assert repo.get("khong-ton-tai") is None
    assert repo.delete(rock.id) is True
    assert repo.get(rock.id) is None
    assert repo.delete(rock.id) is False
