"""SidebarNavigation giữ API kiểu QTabWidget; theme loader ghép QSS (base trước) và nạp font Be Vietnam Pro đóng gói."""

from tests.qt_offscreen_app_helper import get_qapp

from PySide6.QtWidgets import QLabel

from src.ui.dashboard_sidebar_navigation import SidebarNavigation, split_icon_and_label
from src.ui.theme.app_theme_loader import build_stylesheet, register_bundled_fonts
from src.ui.theme.design_tokens import SIDEBAR_RAIL_WIDTH, SIDEBAR_WIDTH


def test_split_icon_and_label():
    assert split_icon_and_label("✅ Tasks & Parking Lot") == ("✅", "Tasks & Parking Lot")
    assert split_icon_and_label("Settings") == ("S", "Settings")


def test_sidebar_tab_api_insert_remove_and_current():
    get_qapp()
    nav = SidebarNavigation("Ted")
    a, b, c = QLabel("a"), QLabel("b"), QLabel("c")
    nav.addTab(a, "✅ A")
    nav.addTab(c, "⚙️ C")
    assert nav.insertTab(1, b, "📚 B & co") == 1
    assert nav.count() == 3 and nav.widget(1) is b and nav.tabText(1) == "📚 B & co"
    assert nav._buttons[1].text() == "📚  B && co"  # '&' được escape khỏi mnemonic

    nav.setCurrentWidget(c)
    assert nav.currentWidget() is c and nav._buttons[2].isChecked()
    nav._buttons[0].click()
    assert nav.currentIndex() == 0 and not nav._buttons[2].isChecked()

    nav.setTabText(2, "⚙️ Settings")
    assert nav.tabText(2) == "⚙️ Settings"
    nav.removeTab(nav.indexOf(b))
    assert nav.count() == 2 and nav.indexOf(b) == -1 and nav.widget(1) is c


def test_sidebar_collapse_shows_icon_rail():
    get_qapp()
    nav = SidebarNavigation("Ted")
    nav.addTab(QLabel("x"), "📔 Journal")
    nav.set_collapsed(True)
    assert nav.sidebar.width() == SIDEBAR_RAIL_WIDTH and nav._buttons[0].text() == "📔"
    assert nav._buttons[0].toolTip() == "📔 Journal"
    nav.set_collapsed(False)
    assert nav.sidebar.width() == SIDEBAR_WIDTH and "Journal" in nav._buttons[0].text()


def test_sidebar_collapse_repolishes_nav_items_with_rail_style():
    get_qapp()
    nav = SidebarNavigation("Ted")
    nav.setStyleSheet(build_stylesheet())
    nav.addTab(QLabel("x"), "📔 Journal")
    nav.set_collapsed(True)
    assert nav._buttons[0].font().pixelSize() == 16  # QFrame#Sidebar[collapsed="true"] QPushButton#NavItem


def test_sidebar_remove_then_add_keeps_visual_order():
    get_qapp()
    nav = SidebarNavigation("Ted")
    for t in ("A", "B", "C", "D"):
        nav.addTab(QLabel(t), t)
    nav.removeTab(0)
    nav.addTab(QLabel("E"), "E")
    layout_order = [nav._nav_layout.itemAt(i).widget() for i in range(nav._nav_layout.count())]
    assert layout_order == nav._buttons


def test_sidebar_emits_current_changed_when_index_shifts():
    get_qapp()
    nav = SidebarNavigation("Ted")
    widgets = [QLabel(t) for t in "ABC"]
    for w in widgets:
        nav.addTab(w, w.text())
    nav.setCurrentWidget(widgets[2])
    seen = []
    nav.currentChanged.connect(seen.append)
    nav.insertTab(0, QLabel("Z"), "Z")
    nav.removeTab(1)
    assert seen == [3, 2] and nav.currentWidget() is widgets[2]


def test_theme_stylesheet_puts_base_first_and_fonts_register():
    get_qapp()
    qss = build_stylesheet()
    assert qss.index("Synthetic Nexus — base") < qss.index("QFrame#Sidebar")
    assert register_bundled_fonts()
