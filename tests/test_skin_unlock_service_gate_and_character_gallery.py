"""Mở khoá nhân vật: đánh giá điều kiện từng loại, vĩnh viễn, cổng set_character, bubble qua Hub, trang Bộ sưu tập (offscreen)."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from sqlmodel import Session

from qt_offscreen_app_helper import get_qapp
from unlockable_skin_test_pack_helper import make_pack

from src.core.gamification.gamification_hub_service import GamificationHubService
from src.core.gamification.hub_snapshot_model import HubSnapshot
from src.core.gamification.skin_unlock_service import SkinUnlockService
from src.core.gamification.xp_ledger_repository import XpLedgerRepository
from src.core.app_state_key_value_store import KeyValueStore
from src.core.models import Task
from src.core.skin_unlock_gate import is_skin_unlocked, set_unlocked_skin_keys
from src.core.unlockable_skin_condition_evaluator import SkinProgressInputs, condition_progress, describe_condition, is_condition_met
from src.core.unlockable_skin_pack_loader import load_unlockable_collection
from src.core.unlockable_skin_registry_model import SkinCondition, UnlockableSkin

FREE, B2 = SkinCondition("free"), SkinCondition("badges", count=2)
GOLD = SkinCondition("badge", badge_id="focus_day_gold")
TASKS3 = SkinCondition("metric", metric="tasks_done", value=3)


@pytest.fixture(autouse=True)
def _reset_gate():
    yield
    set_unlocked_skin_keys(None)


def _skin(key, cond):
    return UnlockableSkin(key, key.split("/")[0], key, key, cond)


def _snap(badges=(), peak=1):
    d = date(2026, 10, 22)
    return HubSnapshot(today=d, week_start=date(2026, 10, 19), level=1, peak_level=peak, pct=50.0,
                       pct_today_delta=0.0, xp_today=0, week_xp=0, active_days=0, decay_days=0, stats={},
                       stats_delta_today={},
                       badges_unlocked=frozenset(badges), distinct_badge_count=len(badges))


def test_condition_evaluation_per_type():
    inputs = SkinProgressInputs(frozenset({"a", "focus_day_gold"}), {"tasks_done": 2.0})
    assert condition_progress(FREE, inputs) == (1, 1) and is_condition_met(FREE, inputs)
    assert condition_progress(B2, inputs) == (2, 2) and is_condition_met(B2, inputs)
    assert is_condition_met(GOLD, inputs) and not is_condition_met(SkinCondition("badge", badge_id="x"), inputs)
    assert condition_progress(TASKS3, inputs) == (2, 3) and not is_condition_met(TASKS3, inputs)
    assert not is_condition_met(SkinCondition("metric", metric="peak_level", value=3), inputs)   # thiếu chỉ số = 0
    assert "2" in describe_condition(B2) and "3" in describe_condition(TASKS3)


def test_unlock_is_permanent_persisted_and_free_is_silent(memory_engine):
    ledger = XpLedgerRepository(memory_engine)
    skins = [_skin("p/free", FREE), _skin("p/b2", B2), _skin("p/gold", GOLD), _skin("p/t3", TASKS3)]
    svc = SkinUnlockService(memory_engine, ledger, skins)
    assert svc.refresh(_snap()) == []                                # free mở nhưng không ăn mừng
    assert svc.unlocked_keys == {"p/free"} and is_skin_unlocked("p/free") and not is_skin_unlocked("p/b2")
    assert is_skin_unlocked("cat")                                   # key gốc (không '/') luôn mở
    new = svc.refresh(_snap({"a", "focus_day_gold"}, peak=2))
    assert {s.key for s in new} == {"p/b2", "p/gold"}
    assert svc.refresh(_snap({"a", "focus_day_gold"})) == []         # không báo lại
    assert svc.refresh(_snap()) == [] and svc.unlocked_keys == {"p/free", "p/b2", "p/gold"}   # tuột huy hiệu: vẫn mở
    assert svc.progress_of(skins[1]) == (2, 2) and svc.progress_of(skins[3]) == (0, 3)
    reborn = SkinUnlockService(memory_engine, ledger, skins)         # khởi động lại app
    assert reborn.unlocked_keys == {"p/free", "p/b2", "p/gold"}
    now = datetime.now(timezone.utc)
    for i in range(3):
        ledger.add(f"task_done:t{i}:1", now, "work", "work", "task_done")
    assert [s.key for s in reborn.refresh(_snap())] == ["p/t3"]      # chỉ số trọn đời từ sổ cái


def test_set_character_rejects_locked_bundled_skin_but_allows_base(monkeypatch):
    from src.config import CHARACTER_SKINS, settings
    from src.core.focus_engine import FocusEngine
    get_qapp()
    monkeypatch.setitem(CHARACTER_SKINS, "p/locked", "🎭 Locked")
    monkeypatch.setattr(settings, "save", lambda: None)
    monkeypatch.setattr(settings, "character_skin", "cat")
    engine = FocusEngine(audio_manager=SimpleNamespace(play_chime=lambda: None))
    changed, nudges = [], []
    engine.character_changed.connect(changed.append)
    engine.external_mcp_message.connect(lambda mood, msg: nudges.append(msg))
    set_unlocked_skin_keys(set())
    engine.set_character("p/locked")
    assert settings.character_skin == "cat" and not changed and len(nudges) == 1
    engine.set_character("owl")                                      # nhân vật gốc không bị cổng chặn
    assert settings.character_skin == "owl" and changed == ["owl"]
    set_unlocked_skin_keys({"p/locked"})
    engine.set_character("p/locked")
    assert settings.character_skin == "p/locked"
    set_unlocked_skin_keys(None)                                     # không có Hub → cho phép tất cả (hành vi cũ)
    engine.set_character("p/locked")


def test_hub_refresh_announces_new_skin_with_bubble_and_signal(memory_engine):
    get_qapp()
    said = []
    bubble = SimpleNamespace(is_busy=lambda: False, show_message=lambda text, mood=None, **_: said.append(text))
    ctx = SimpleNamespace(kv=KeyValueStore(memory_engine), registry=None, focus_engine=None, bubble=bubble)
    skins = [_skin("p/one", SkinCondition("badges", count=1)), _skin("p/far", SkinCondition("badges", count=40))]
    svc = GamificationHubService(ctx, memory_engine, skins=skins)
    with Session(memory_engine, expire_on_commit=False) as s:
        s.add_all([Task(title=str(i), status="done", updated_at=datetime.now(timezone.utc)) for i in range(20)])
        s.commit()
    got = []
    svc.skins_unlocked.connect(got.append)
    svc.refresh()
    assert [x.key for x in got[0]] == ["p/one"] and any("🎭" in m and "p/one" in m for m in said)
    assert svc.skin_unlocks.unlocked_keys == {"p/one"} and not is_skin_unlocked("p/far")
    svc.refresh()
    assert len(got) == 1                                             # không báo lại lần nữa


def test_get_character_skins_lists_only_unlocked_bundled(monkeypatch):
    from src.config import CHARACTER_SKINS
    from src.core.i18n import get_character_skins
    monkeypatch.setitem(CHARACTER_SKINS, "p/a", "🎭 A")
    monkeypatch.setitem(CHARACTER_SKINS, "p/b", "🎭 B")
    set_unlocked_skin_keys({"p/a"})
    skins = get_character_skins("vi")
    assert "p/a" in skins and "p/b" not in skins and "cat" in skins


def test_gallery_widget_offscreen_smoke(tmp_path, monkeypatch):
    from src.config import settings
    from src.core.focus_engine import FocusEngine
    from src.ui import character_gallery_entries_and_images as entries
    from src.ui.dashboard_tabs.character_gallery_tab_widget import CharacterGalleryTabWidget
    get_qapp()
    make_pack(tmp_path / "pk", chars=("aa", "bb", "cc"), size=(256, 384))
    col = load_unlockable_collection(tmp_path)
    monkeypatch.setattr(entries, "UNLOCKABLE_SKINS", col.skins)
    monkeypatch.setattr(entries, "PACK_CHARACTERS", dict(col.characters))
    monkeypatch.setattr(entries, "UNLOCKABLE_PACK_TITLES", col.pack_titles)
    monkeypatch.setitem(__import__("src.config", fromlist=["CHARACTER_SKINS"]).CHARACTER_SKINS, "pk/aa", "🎭 AA")
    monkeypatch.setattr(settings, "save", lambda: None)
    monkeypatch.setattr(settings, "character_skin", "cat")
    set_unlocked_skin_keys({col.skins[0].key})
    focus = FocusEngine(audio_manager=SimpleNamespace(play_chime=lambda: None))
    tab = CharacterGalleryTabWidget(focus)
    tab.resize(780, 560)
    tab.show()
    tab.refresh()
    assert len(tab._cards) >= 6 + 3 and tab.lbl_summary.text().startswith("Đã mở")
    first, second = (tab._cards[s.key] for s in col.skins[:2])
    assert not first.locked and second.locked and second.bar.isVisible()
    tab._on_card_clicked(second.entry.key)                           # khoá: nút Dùng bị tắt
    assert not tab.preview.btn_use.isEnabled()
    tab._on_card_clicked(first.entry.key)
    assert tab.preview.btn_use.isEnabled()
    tab.preview.btn_use.click()                                      # dùng nhân vật đã mở
    assert settings.character_skin == first.entry.key and not tab.preview.btn_use.isEnabled()
    assert not tab.grab().isNull()
    tab.close()


def test_gallery_search_filter_and_personality_display(tmp_path, monkeypatch):
    from src.config import settings
    from src.core.focus_engine import FocusEngine
    from src.ui import character_gallery_entries_and_images as entries
    from src.ui.dashboard_tabs.character_gallery_tab_widget import CharacterGalleryTabWidget
    get_qapp()
    make_pack(tmp_path / "pk", chars=("aa", "bb", "cc"), size=(256, 384))
    col = load_unlockable_collection(tmp_path)
    monkeypatch.setattr(entries, "UNLOCKABLE_SKINS", col.skins)
    monkeypatch.setattr(entries, "PACK_CHARACTERS", dict(col.characters))
    monkeypatch.setattr(entries, "UNLOCKABLE_PACK_TITLES", col.pack_titles)
    monkeypatch.setitem(__import__("src.config", fromlist=["CHARACTER_SKINS"]).CHARACTER_SKINS, "pk/aa", "🎭 AA")
    monkeypatch.setattr(settings, "save", lambda: None)
    monkeypatch.setattr(settings, "character_skin", "cat")
    set_unlocked_skin_keys({col.skins[0].key, "cat"})

    focus = FocusEngine(audio_manager=SimpleNamespace(play_chime=lambda: None))
    tab = CharacterGalleryTabWidget(focus)
    tab.resize(800, 600)
    tab.show()
    tab.refresh()

    # 1. Thẻ hiển thị cá tính
    cat_card = tab._cards["cat"]
    assert cat_card.lbl_personality.isVisible()
    assert "Vui vẻ" in cat_card.lbl_personality.text()

    # 2. Khung xem trước hiển thị cá tính, mô tả, tags
    tab._on_card_clicked("cat")
    assert tab.preview.lbl_personality.isVisible()
    assert "Vui vẻ" in tab.preview.lbl_personality.text()
    assert tab.preview.lbl_personality_desc.isVisible()
    assert tab.preview.lbl_tags.isVisible()
    assert "#Có sẵn" in tab.preview.lbl_tags.text() or "#Có" in tab.preview.lbl_tags.text()

    # 3. Tìm kiếm theo tên
    tab.txt_search.setText("Shiba")
    visible_keys = [k for k, c in tab._cards.items() if c.isVisible()]
    assert "shiba" in visible_keys
    assert "cat" not in visible_keys

    # 4. Tìm kiếm không phân biệt chữ hoa thường hoặc theo tag
    tab.txt_search.setText("động vật")
    visible_keys = [k for k, c in tab._cards.items() if c.isVisible()]
    assert "cat" in visible_keys and "shiba" in visible_keys

    # 5. Lọc theo nút tag: "unlocked" (chỉ hiện nhân vật đã mở)
    tab.txt_search.clear()
    tab._on_tag_button_clicked("unlocked")
    visible_keys = [k for k, c in tab._cards.items() if c.isVisible()]
    assert "cat" in visible_keys and col.skins[0].key in visible_keys
    assert col.skins[1].key not in visible_keys

    # 6. Lọc theo nút tag cá tính: "Điềm tĩnh" (Owl)
    tab._on_tag_button_clicked("Điềm tĩnh")
    visible_keys = [k for k, c in tab._cards.items() if c.isVisible()]
    assert "owl" in visible_keys
    assert "cat" not in visible_keys

    # 7. Tìm kiếm không ra kết quả -> hiện thông báo rỗng & nút xóa bộ lọc
    tab.txt_search.setText("ten_nhan_vat_khong_ton_tai_xyz123")
    visible_keys = [k for k, c in tab._cards.items() if c.isVisible()]
    assert len(visible_keys) == 0
    assert tab._empty_container.isVisible()

    # 8. Bấm nút xóa bộ lọc khôi phục toàn bộ thẻ
    tab.btn_clear_filters.click()
    assert tab.txt_search.text() == ""
    assert tab._selected_tag == "all"
    assert not tab._empty_container.isVisible()
    assert all(c.isVisible() for c in tab._cards.values())

    # 9. select_character tự động giải tỏa bộ lọc nếu nhân vật đang bị ẩn
    tab.txt_search.setText("shiba")
    assert tab._cards["cat"].isHidden()
    tab.select_character("cat")
    assert not tab._cards["cat"].isHidden()
    assert tab._selected == "cat"

    tab.close()
