import logging

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QMenu, QPushButton, QWidget
from src.core.focus_engine import FocusState
from src.core.i18n import i18n, tr
from src.config import PACK_CHARACTERS, CHARACTER_SKINS, DEFAULT_CHARACTER_SKIN, get_resource_path, settings
from src.core.background_task_spawner import spawn_background_task
from src.core.character_pack_loader import MOOD_TO_STATE, STATE_IDS
from src.ui.companion_context_menu_builder import build_companion_context_menu
from src.ui.companion_pet_painter import paint_companion
from src.ui.pet_click_controller import PetClickController
from src.ui.pet_level_chip import LevelChipTracker, chip_contains
from src.ui.flat_icon_loader import get_flat_icon

logger = logging.getLogger("ted")

PACK_PIXMAP_PX = 192   # cạnh dài ảnh Character Pack sau khi thu nhỏ (ô avatar 96px x HiDPI 2x)
FOCUS_NUDGE_BUBBLE_MS = 12_000   # nhắc trong Deep Work: tự ẩn nếu không trả lời


class TedCompanionWidget(QWidget):
    """
    Cửa sổ nổi trong suốt (Frameless, Always-on-Top, Tool Window) hiển thị nhân vật đồng hành và đồng hồ Pomodoro.
    Vẽ → companion_pet_painter, menu chuột phải → companion_context_menu_builder,
    click đơn/đúp → PetClickController (đơn: engine.on_pet_click hoặc câu động viên; đúp: Quick Chat).
    """

    MOOD_SUFFIX_MAP = MOOD_TO_STATE

    def __init__(self, ctx, cheer_provider):
        super().__init__()
        self.ctx = ctx
        self.focus_engine = ctx.focus_engine
        self.quick_chat = ctx.quick_chat
        self._cheer_provider = cheer_provider

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(300, 140)

        self._drag_offset = QPoint()
        self._press_global = QPoint()
        self._was_dragged = False
        self._breath_phase = 0.0
        self._is_hovered = False
        self._bounce_scale = 1.0
        self.setMouseTracking(True)
        # click 5 lần (hành động ẩn, ghi trong tab Trợ giúp) → popup tên / tính cách / giọng riêng của nhân vật
        self._clicks = PetClickController(self._on_single_click, self._on_double_click, parent=self,
                                          on_multi=self.open_persona_dialog)
        self._persona_dialog = None
        self._chip_tracker = LevelChipTracker()
        self._chip_pressed = False
        self._connect_level_chip(getattr(ctx, "gamification", None))

        self.svg_renderer = QSvgRenderer(self)
        self._current_pixmap = None
        self._pack_pixmap_cache: dict = {}    # {Path ảnh pack: QPixmap đã thu nhỏ}
        self._pack_warmed_skins: set[str] = set()
        self._load_character_mood_svg(settings.character_skin, "IDLE")

        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(40)
        self.anim_timer.timeout.connect(self._on_breath_step)
        self.anim_timer.start()

        fe = self.focus_engine
        fe.state_changed.connect(lambda state, mood: self._load_character_mood_svg(settings.character_skin, mood))
        fe.character_changed.connect(lambda skin: self._load_character_mood_svg(skin, fe.current_mood))
        fe.timer_tick.connect(lambda *_: self.update())
        fe.mindful_ping_triggered.connect(self._on_mindful_ping)
        fe.external_mcp_message.connect(self._on_external_nudge)

        self.btn_pomo_action = QPushButton(self)
        self.btn_pomo_action.setObjectName("PomoActionBtn")
        self.btn_pomo_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pomo_action.clicked.connect(self._on_pomo_action_clicked)

        self.btn_pomo_stop = QPushButton(self)
        self.btn_pomo_stop.setObjectName("PomoStopBtn")
        self.btn_pomo_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pomo_stop.clicked.connect(self._on_pomo_stop_clicked)

        self.btn_pomo_break = QPushButton(self)
        self.btn_pomo_break.setObjectName("PomoBreakBtn")
        self.btn_pomo_break.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pomo_break.setIcon(get_flat_icon("break", 16))
        self.btn_pomo_break.setIconSize(QSize(16, 16))
        self.btn_pomo_break.clicked.connect(self._on_pomo_break_clicked)

        self.btn_pomo_meeting = QPushButton(self)
        self.btn_pomo_meeting.setObjectName("PomoMeetingBtn")
        self.btn_pomo_meeting.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pomo_meeting.setIcon(get_flat_icon("meeting", 16))
        self.btn_pomo_meeting.setIconSize(QSize(16, 16))
        self.btn_pomo_meeting.clicked.connect(self._on_pomo_meeting_clicked)

        self._update_pomo_buttons()
        fe.state_changed.connect(lambda *_: self._update_pomo_buttons())
        i18n.language_changed.connect(lambda *_: self._update_pomo_buttons())

        self._place_bottom_right()
        if ctx.bubble is not None:
            ctx.bubble.follow(self)

    @staticmethod
    def _style_pomo_button(btn: QPushButton, kind: str) -> None:
        """Đặt kiểu nút qua thuộc tính động `pomoKind` (định nghĩa trong theme/qss/40-pet.qss) rồi áp lại style."""
        btn.setProperty("pomoKind", kind)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    @staticmethod
    def _with_hotkey(label: str, action_id: str) -> str:
        try:
            from src.core.hotkeys.global_hotkey_manager import hotkey_manager
            hint = hotkey_manager.display_text(action_id)
            return f"{label} ({hint})" if hint else label
        except Exception:
            return label

    def _update_pomo_buttons(self):
        state = self.focus_engine.state
        action, stop = self.btn_pomo_action, self.btn_pomo_stop
        btn_break, btn_meeting = self.btn_pomo_break, self.btn_pomo_meeting
        # (ký hiệu, tooltip text, kiểu nút) theo trạng thái
        if state == FocusState.DEEP_WORK_RUNNING:
            glyph, tip, kind = "⏸", self._with_hotkey(tr("pomo_btn_pause_tooltip"), "focus.toggle"), "pause"
        elif state == FocusState.PAUSED:
            glyph, tip, kind = "▶", self._with_hotkey(tr("pomo_btn_resume_tooltip"), "focus.toggle"), "resume"
        elif state == FocusState.BREAK_RUNNING:
            glyph, tip, kind = "☕", tr("menu_break_short"), "break"
        elif state == FocusState.MEETING_RUNNING:
            glyph, tip, kind = "👥", self._with_hotkey(tr("pomo_btn_stop_meeting_tooltip"), "meeting.toggle"), "break"
        else:
            glyph, tip, kind = "▶", self._with_hotkey(tr("pomo_btn_start_tooltip"), "focus.toggle"), "start"
        session_active = kind != "start"

        if session_active:
            # 2 nút khi đang trong phiên (tâm 188): action (154) và stop (194)
            action.setGeometry(154, 92, 28, 28)
            if state == FocusState.BREAK_RUNNING:
                action.setIcon(get_flat_icon("break", 16))
                action.setIconSize(QSize(16, 16))
                action.setText("")
            elif state == FocusState.MEETING_RUNNING:
                action.setIcon(get_flat_icon("meeting", 16))
                action.setIconSize(QSize(16, 16))
                action.setText("")
            else:
                from PySide6.QtGui import QIcon
                action.setIcon(QIcon())
                action.setText(glyph)
            action.setToolTip(tip)
            self._style_pomo_button(action, kind)
            action.show()

            stop.setGeometry(194, 92, 28, 28)
            stop.setText("⏹")
            stop.setToolTip(self._with_hotkey(tr("pomo_btn_stop_tooltip"), "focus.stop"))
            stop.show()

            btn_break.hide()
            btn_meeting.hide()
        else:
            from PySide6.QtGui import QIcon
            # IDLE: 3 nút đối xứng qua tâm 188 của pill: [☕ Nghỉ: 134] [▶ Bắt đầu: 174] [👥 Họp: 214]
            btn_break.setGeometry(134, 92, 28, 28)
            btn_break.setIcon(get_flat_icon("break", 16))
            btn_break.setIconSize(QSize(16, 16))
            btn_break.setText("")
            btn_break.setToolTip(self._with_hotkey(tr("pomo_btn_break_tooltip"), "break.start"))
            btn_break.show()

            action.setGeometry(174, 92, 28, 28)
            action.setIcon(QIcon())
            action.setText(glyph)
            action.setToolTip(tip)
            self._style_pomo_button(action, kind)
            action.show()

            btn_meeting.setGeometry(214, 92, 28, 28)
            btn_meeting.setIcon(get_flat_icon("meeting", 16))
            btn_meeting.setIconSize(QSize(16, 16))
            btn_meeting.setText("")
            btn_meeting.setToolTip(self._with_hotkey(tr("pomo_btn_meeting_tooltip"), "meeting.toggle"))
            btn_meeting.show()

            stop.hide()

    def _on_pomo_action_clicked(self):
        if self.focus_engine.state in (FocusState.BREAK_RUNNING, FocusState.MEETING_RUNNING):
            self.focus_engine.stop_session(completed=False)
        else:
            self.focus_engine.pause_or_resume()

    def _on_pomo_stop_clicked(self):
        self.focus_engine.stop_session(completed=False)

    def _on_pomo_break_clicked(self):
        self.focus_engine.start_break()

    def _on_pomo_meeting_clicked(self):
        from src.ui.meeting_mode.meeting_entry_point_helpers import request_meeting_toggle
        request_meeting_toggle(self.focus_engine)

    def _place_bottom_right(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.right() - self.width() - 28, geo.bottom() - self.height() - 36)

    def _pack_pixmap(self, image):
        """Ảnh pack đã thu nhỏ, cache theo đường dẫn: decode + scale (ảnh tới 1024x1536) chỉ 1 lần mỗi file."""
        if image is None:
            return None
        pixmap = self._pack_pixmap_cache.get(image)
        if pixmap is None:
            # 2x ô 96px cho màn HiDPI → vẽ mỗi khung hình nhẹ
            pixmap = QPixmap(str(image)).scaled(PACK_PIXMAP_PX, PACK_PIXMAP_PX, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation)
            self._pack_pixmap_cache[image] = pixmap
        return pixmap

    def _load_character_mood_svg(self, skin: str, mood: str):
        skin_key = skin if skin in CHARACTER_SKINS else DEFAULT_CHARACTER_SKIN
        suffix = self.MOOD_SUFFIX_MAP.get(mood, "idle")

        character = PACK_CHARACTERS.get(skin_key)   # Character Pack / nhân vật bundle: PNG theo trạng thái
        if character is not None:   # (thiếu trạng thái → idle → avatar); 6 con vật gốc không có trong map
            if skin_key not in self._pack_warmed_skins:   # nạp sẵn cả 5 trạng thái 1 lần → đổi mood không bị giật
                self._pack_warmed_skins.add(skin_key)
                for state in STATE_IDS:
                    self._pack_pixmap(character.image_for(state))
            self._current_pixmap = self._pack_pixmap(character.image_for(suffix))
            self.update()
            return

        # Ưu tiên ảnh PNG Chibi độ nét cao từ thư mục preview hoặc animations, sau đó mới tới SVG
        png_path = get_resource_path(f"assets/animations_png_preview/{skin_key}_{suffix}.png")
        if not png_path.exists():
            png_path = get_resource_path(f"../docs/UI/animations_png_preview/{skin_key}_{suffix}.png")
        if not png_path.exists():
            png_path = get_resource_path(f"assets/animations/{skin_key}_{suffix}.png")

        if png_path.exists():
            self._current_pixmap = QPixmap(str(png_path))
        else:
            self._current_pixmap = None
            svg_path = get_resource_path(f"assets/animations/{skin_key}_{suffix}.svg")
            if not svg_path.exists():
                svg_path = get_resource_path(f"assets/animations/cat_{suffix}.svg")
            if svg_path.exists():
                self.svg_renderer.load(str(svg_path))
        self.update()

    def _on_breath_step(self):
        self._breath_phase = (self._breath_phase + 0.10) % 6.28318
        target_scale = 1.05 if self._is_hovered else 1.0
        self._bounce_scale += (target_scale - self._bounce_scale) * 0.16
        self.update()

    def _on_mindful_ping(self, task_title: str):
        bubble = self.ctx.bubble
        if bubble is None:
            self.quick_chat.show_mindful_ping(task_title)
            return
        # Deep Work: không bật popup to — hỏi nhẹ ở bubble, không trả lời thì tự ẩn; bubble đang bận (chat/nhắc khác) → bỏ qua lượt này
        if bubble.is_busy():
            self.focus_engine.set_mood("FOCUS")
            return
        bubble.show_message(
            tr("ping_bubble_question", task=task_title),
            mood="GENTLE_NUDGE",
            actions=[
                (tr("ping_btn_focused"), lambda: self.focus_engine.set_mood("FOCUS")),
                (tr("ping_btn_distracted"), self._on_ping_distracted),
            ],
            timeout_ms=FOCUS_NUDGE_BUBBLE_MS,
        )
        QTimer.singleShot(FOCUS_NUDGE_BUBBLE_MS, self._restore_focus_mood)

    def _on_ping_distracted(self):
        self.focus_engine.record_distraction()
        self.focus_engine.set_mood("FOCUS")
        self.ctx.bubble.show_message(tr("ping_bubble_ack_distracted"), mood="FOCUS", timeout_ms=3000)

    def _restore_focus_mood(self):
        """Hết giờ nhắc mà không trả lời → mặt Ted về FOCUS, không giữ vẻ 'nhắc nhở' suốt phiên."""
        fe = self.focus_engine
        if fe.state == FocusState.DEEP_WORK_RUNNING and fe.current_mood == "GENTLE_NUDGE":
            fe.set_mood("FOCUS")

    def _on_external_nudge(self, mood: str, message: str):
        """Lời nhắc của AI: lưu vào trang Chat + hiện ở bubble nhỏ, không bật cả app lên."""
        if hasattr(self.quick_chat, "show_ai_nudge"):
            self.quick_chat.show_ai_nudge(mood, message)
        elif hasattr(self.quick_chat, "show_hermes_nudge"):
            self.quick_chat.show_hermes_nudge(mood, message)
        bubble = self.ctx.bubble
        if bubble is not None and not bubble.is_busy():   # không chen ngang chat đang mở trong bubble
            bubble.show_message(message, mood=mood, timeout_ms=FOCUS_NUDGE_BUBBLE_MS)
        if self.focus_engine.state == FocusState.DEEP_WORK_RUNNING:
            QTimer.singleShot(FOCUS_NUDGE_BUBBLE_MS, self._restore_focus_mood)

    def _connect_level_chip(self, hub) -> None:
        """Chip level đọc snapshot/level_changed của Hub; không có Hub → không chip."""
        if hub is None:
            return
        hub.snapshot_changed.connect(lambda snap: (self._chip_tracker.on_snapshot(snap), self.update()))
        hub.level_changed.connect(lambda old, new: (self._chip_tracker.on_level_changed(old, new), self.update()))
        if hub.current_snapshot is not None:
            self._chip_tracker.on_snapshot(hub.current_snapshot)

    def level_chip(self):
        return self._chip_tracker.chip()

    def open_dashboard(self):
        dash = self.ctx.dashboard
        dash.refresh_all()
        dash.show()
        dash.raise_()
        dash.activateWindow()

    # ---- click đơn / đúp ----
    def _on_single_click(self):
        from src.core.tts_service import tts_service
        if tts_service.is_speaking():  # Ted đang nói → click để im ngay câu đó (giọng đọc vẫn bật)
            tts_service.stop()
            return
        host = self.ctx.engine_host
        engine = host.active_engine() if host else None
        try:
            if engine is not None and engine.on_pet_click():
                return
        except Exception:
            logger.exception("on_pet_click lỗi")
        if self.ctx.bubble is None:
            spawn_background_task(self._cheer_provider.show_cheer(), "pet-cheer")
            return
        if self.ctx.bubble.has_pending_actions():   # đang có nhắc kèm nút (họp, briefing...) → không ghi đè
            return
        # click đơn → bubble chat nhỏ; câu động viên + việc đang làm/Q1 là dòng đầu của Ted
        self.ctx.bubble.open_chat(module_id=self._active_module_id())
        spawn_background_task(self._cheer_provider.show_cheer_in_chat(), "pet-cheer-chat")

    def open_persona_dialog(self):
        from src.ui.character_persona_dialog import CharacterPersonaDialog
        if self._persona_dialog is not None and self._persona_dialog.isVisible():
            self._persona_dialog.raise_()
            return self._persona_dialog
        dialog = CharacterPersonaDialog(settings.character_skin)
        dialog.persona_saved.connect(self._on_persona_saved)
        self._persona_dialog = dialog
        dialog.show()
        return dialog

    def _on_persona_saved(self, skin: str):
        if skin != settings.character_skin or self.ctx.bubble is None:
            return
        from src.core.character_persona_profiles import saved_persona
        persona = saved_persona(skin)
        self.ctx.bubble.retranslate_ui()   # cập nhật tên nhân vật trên header bong bóng chat
        if persona is not None:
            self.ctx.bubble.show_message(persona.greeting(), mood="CHEER")

    def _active_module_id(self) -> str:
        active = self.ctx.registry.active()
        return active.id if active else "work"

    def _on_double_click(self):
        if self.ctx.bubble is not None:
            self.ctx.bubble.hide()   # chat to trong app thay cho bubble đang mở
        self.quick_chat.open_for(self._active_module_id())   # → trang 💬 Chat trong Dashboard

    # ---- sự kiện chuột ----
    def paintEvent(self, event):
        painter = QPainter(self)
        paint_companion(painter, self)

    def enterEvent(self, event):
        self._is_hovered = True
        self._bounce_scale = 1.10
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def moveEvent(self, event):
        if self.ctx.bubble is not None:
            self.ctx.bubble.reposition()
        super().moveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.level_chip() and chip_contains(event.position()):
            self._chip_pressed = True   # bấm chip level → mở Hub, không kéo/click pet
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._was_dragged = False
            self._press_global = event.globalPosition().toPoint()
            self._bounce_scale = 0.92
            self.update()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._chip_pressed:   # nhấn từ chip level: không kéo pet (offset/điểm nhấn còn của lần trước)
            event.accept()
            return
        if event.buttons() & Qt.MouseButton.LeftButton:
            moved = (event.globalPosition().toPoint() - self._press_global).manhattanLength()
            if not self._was_dragged and moved < QApplication.startDragDistance():
                event.accept()  # rung tay vài px không tính là kéo → vẫn là click
                return
            self._was_dragged = True
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._chip_pressed:
            self._chip_pressed = False
            if chip_contains(event.position()):
                self.ctx.dashboard.open_hub()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._bounce_scale = 1.12
            self.update()
            self._clicks.on_release(self._was_dragged)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._clicks.on_double_click()
            event.accept()

    def contextMenuEvent(self, event):
        menu = build_companion_context_menu(QMenu(self), self.ctx, self)
        menu.exec(event.globalPos())
        menu.deleteLater()  # mỗi lần chuột phải tạo menu mới → tránh tích tụ con của widget
