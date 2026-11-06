"""Hub UI (offscreen): trang Hub hiển thị snapshot, nút đi chơi có trần, chip level + click, menu/tray, phím tắt, i18n."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QMenu, QPushButton

from tests.qt_offscreen_app_helper import get_qapp
from tests.hub_ui_test_fixtures_helper import FakeHubService, fake_focus_engine, make_snapshot

from src.core.gamification.wellbeing_daily_repository import MAX_OUTINGS_PER_DAY, WellbeingDailyRepository
from src.core.i18n import TRANSLATIONS, i18n


@pytest.fixture(autouse=True)
def _vi():
    i18n.set_language("vi")
    yield
    i18n.set_language("vi")


@pytest.fixture
def hub(memory_engine):
    get_qapp()
    return FakeHubService(WellbeingDailyRepository(memory_engine), make_snapshot())


@pytest.fixture
def window(hub, tmp_path):
    from src.config import AppConfig
    from src.modules_runtime.module_registry_loader import ModuleRegistry
    from src.ui.dashboard_window import DashboardWindow

    win = DashboardWindow(fake_focus_engine(), ModuleRegistry(AppConfig(data_dir=tmp_path), dirs=[]))
    win.bind_gamification(hub)
    return win


def test_hub_strings_have_vi_en_parity():
    hub_keys = lambda lang: {k for k in TRANSLATIONS[lang] if k.startswith("hub_") or k in ("tab_hub", "menu_hub", "tray_hub")}
    assert hub_keys("vi") == hub_keys("en") and len(hub_keys("vi")) > 40


def test_hub_tab_sits_after_analytics_and_renders_snapshot(window):
    tab = window.hub_tab
    assert window.tabs.indexOf(tab) == window.tabs.indexOf(window.analytics_tab) + 1
    assert window.tabs.tabText(window.tabs.indexOf(tab)) == "🏆 Hub của Ted"
    h = tab.header
    assert h.lbl_level.text() == "Cấp 6 / 10 · 57%" and h.bar.value() == 57 and "12 / 20" in h.lbl_today.text()
    assert 0 < h.bar.value() < h.bar.maximum()
    visible_stats = [k for k, (n, b, v) in tab.stats._rows.items() if not n.isHidden()]
    assert len(visible_stats) == 6
    assert tab.stats._rows["screen_load"][1].property("tone") == "warn"   # 82 ≥ 70
    assert tab.stats._rows["energy"][1].property("tone") == "ok"
    grid = tab.badges
    assert len(grid._tiles) >= 50 and grid.lbl_owned.text() == f"Đã có 17/{len(grid._tiles)}"
    owned = [t for t in grid._tiles if t.unlocked]
    assert len(owned) == 17 and all(t.property("locked") is False for t in owned)
    assert any(t.property("locked") is True for t in grid._tiles)
    table = tab.weekly_log.table
    assert table.rowCount() == 6   # tuần đang diễn ra + 5 tuần đã lưu
    assert "(đang diễn ra)" in table.item(0, 0).text()
    assert table.item(1, 1).text().endswith("▲")   # cấp 5 so với 4


def test_hub_tab_hides_learning_row_when_none_and_filters_badges(window, hub):
    snap = make_snapshot()
    stats = dict(snap.stats, learning=None)
    from dataclasses import replace
    hub.snapshot_changed.emit(replace(snap, stats=stats))
    assert window.hub_tab.stats._rows["learning"][0].isHidden()
    grid = window.hub_tab.badges
    idx = grid.combo.findData("focus")
    grid.combo.setCurrentIndex(idx)
    shown = [t for t in grid._tiles if not t.isHidden()]
    assert shown and all(t.badge.category == "focus" for t in shown)


def test_language_switch_retitles_hub(window):
    i18n.set_language("en")
    window.retranslate_ui()
    window.hub_tab.retranslate_ui()
    assert window.tabs.tabText(window.tabs.indexOf(window.hub_tab)) == "🏆 Ted Hub"
    assert window.hub_tab.header.lbl_level.text() == "Level 6 / 10 · 57%"
    assert window.hub_tab.badges.lbl_owned.text().startswith("Owned 17/")


def test_outing_button_logs_and_caps_at_three(window, hub):
    stats = window.hub_tab.stats
    for n in range(MAX_OUTINGS_PER_DAY):
        assert stats.btn_outing.isEnabled()
        stats.btn_outing.click()
    assert hub.wellbeing.get(date.today()).outings == MAX_OUTINGS_PER_DAY
    assert hub.refresh_requests == MAX_OUTINGS_PER_DAY
    assert not stats.btn_outing.isEnabled() and "3" in stats.lbl_outing_status.text()
    stats.combo_day.setCurrentIndex(1)   # hôm qua còn trống
    assert stats.btn_outing.isEnabled()
    assert stats.combo_day.count() == 7


def test_open_hub_switches_page_and_requests_refresh(window, hub):
    window.open_hub()
    assert window.tabs.currentWidget() is window.hub_tab and hub.refresh_requests == 1


def test_teaser_button_opens_gallery(window):
    window.hub_tab.characters.btn_gallery.click()
    assert window.tabs.currentWidget() is window.gallery_tab
    assert "/" in window.hub_tab.characters.lbl_summary.text()


def _companion(hub, opened):
    from src.core.focus_engine import FocusEngine
    from src.ui.companion_widget import TedCompanionWidget

    focus = FocusEngine(audio_manager=SimpleNamespace(play_chime=lambda: None, toggle_ambient=lambda: None, is_ambient_playing=False))
    ctx = SimpleNamespace(focus_engine=focus, bubble=None, gamification=hub,
                          quick_chat=SimpleNamespace(show_mindful_ping=lambda t: None, show_hermes_nudge=lambda m, s: None),
                          dashboard=SimpleNamespace(open_hub=lambda: opened.append(1)))
    return TedCompanionWidget(ctx, cheer_provider=SimpleNamespace(show_cheer=lambda: None))


def test_level_chip_text_states_and_click_opens_hub(hub):
    from PySide6.QtTest import QTest
    from src.ui.pet_level_chip import CHIP_RECT

    opened = []
    widget = _companion(hub, opened)
    assert widget.level_chip() == ("Lv6", "normal")
    hub.level_changed.emit(5, 6)
    assert widget.level_chip() == ("Lv6", "up")
    hub.level_changed.emit(6, 5)
    hub.snapshot_changed.emit(make_snapshot(level=5))
    assert widget.level_chip() == ("Lv5", "down")
    image = QImage(300, 140, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    from src.ui.companion_pet_painter import paint_companion
    paint_companion(painter, widget)
    painter.end()
    widget.show()
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=CHIP_RECT.center().toPoint())
    assert opened == [1]
    assert not widget._chip_pressed
    before = widget.pos()                                     # nhấn chip rồi rê chuột: pet không bị kéo/nhảy
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=CHIP_RECT.center().toPoint())
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent
    move = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(200, 60), widget.mapToGlobal(QPointF(200, 60)),
                       Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    widget.mouseMoveEvent(move)
    assert widget.pos() == before
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=CHIP_RECT.center().toPoint())


def test_no_hub_means_no_chip():
    get_qapp()
    from src.ui.pet_level_chip import LevelChipTracker
    assert LevelChipTracker().chip() is None


def test_chip_tracker_up_glow_expires_after_ten_minutes():
    from src.ui.pet_level_chip import LevelChipTracker
    t = LevelChipTracker()
    t.on_snapshot(make_snapshot(level=3))
    now = datetime(2026, 10, 22, 9, 0)
    t.on_level_changed(2, 3, now)
    assert t.chip(now.replace(minute=9)) == ("Lv3", "up")
    assert t.chip(now.replace(minute=11)) == ("Lv3", "normal")


def test_context_menu_has_hub_entry_only_with_gamification(hub):
    from src.core.focus_engine import FocusState
    from src.ui.companion_context_menu_builder import build_companion_context_menu

    get_qapp()
    opened, keep = [], []

    def build(gamification):
        ctx = SimpleNamespace(
            focus_engine=SimpleNamespace(state=FocusState.IDLE, pause_or_resume=lambda: None),
            registry=SimpleNamespace(active=lambda: None, enabled=lambda: []),
            audio=SimpleNamespace(is_ambient_playing=False, toggle_ambient=lambda: None),
            engine_host=None, gamification=gamification,
            dashboard=SimpleNamespace(open_settings=lambda: None, open_hub=lambda: opened.append(1)))
        menu = build_companion_context_menu(QMenu(), ctx, SimpleNamespace(open_dashboard=lambda: None, hide=lambda: None))
        keep.append(menu)   # giữ menu sống để QAction không bị xoá
        return {a.text().split("\t")[0]: a for a in menu.actions()}

    assert "🏆 Hub của Ted" not in build(None)
    entry = build(hub)["🏆 Hub của Ted"]
    entry.trigger()
    assert opened == [1]


def test_tray_menu_has_hub_entry_after_bind(window, monkeypatch):
    from src.ui import tray_manager as tm

    monkeypatch.setattr(tm, "QSystemTrayIcon", _FakeTray)
    focus = SimpleNamespace(session_completed=SimpleNamespace(connect=lambda f: None), pause_or_resume=lambda: None)
    tray = tm.TrayManager(companion_widget=SimpleNamespace(), dashboard_window=window, focus_engine=focus,
                          audio_manager=SimpleNamespace(toggle_ambient=lambda: None))
    titles = [a.text().split("\t")[0] for a in tray.tray.contextMenu().actions()]
    assert "🏆 Hub của Ted" in titles


class _FakeTray:
    class ActivationReason:
        Trigger = 1

    def __init__(self):
        self._menu = None
        self.activated = SimpleNamespace(connect=lambda f: None)

    def setIcon(self, icon): pass
    def setToolTip(self, text): pass
    def show(self): pass
    def setContextMenu(self, menu): self._menu = menu
    def contextMenu(self): return self._menu


def test_hub_open_hotkey_is_bound_to_real_dashboard(window):
    from tests.test_global_hotkey_manager_with_fake_backends import make_manager
    from src.ui.hotkey_default_action_callbacks_wiring import wire_default_hotkey_actions

    mgr, native, _ = make_manager()
    ctx = SimpleNamespace(focus_engine=SimpleNamespace(pause_or_resume=lambda: None, stop_session=lambda completed: None,
                                                       start_break=lambda: None),
                          quick_chat=None, dashboard=window, registry=None)
    wire_default_hotkey_actions(ctx, SimpleNamespace(open_dashboard=lambda: None), SimpleNamespace(toggle_companion=lambda: None), mgr)
    mgr.apply({})
    assert mgr.status("hub.open") == "global"
    mgr._callbacks["hub.open"]()
    assert window.tabs.currentWidget() is window.hub_tab
