#!/usr/bin/env python3
"""
Điểm khởi chạy chính của ứng dụng Ted Desktop Companion (PySide6 + qasync + Hermes Agent).
"""

import asyncio
import logging
import sys
from pathlib import Path

# Đảm bảo import được package src khi chạy trực tiếp `python src/main.py`
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import src.core.python315_lazy_import_workaround  # noqa: F401  (phải đứng trước PySide6)

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    import qasync
except ModuleNotFoundError as e:
    missing_mod = e.name
    print(f"\n[LỖI] Không tìm thấy thư viện '{missing_mod}'.")
    print("Bạn đang chạy bằng Python hệ thống thay vì môi trường ảo (.venv) của dự án.\n")
    print("👉 Hãy chạy ứng dụng bằng một trong các cách sau:")
    print("   Cách 1 (Kích hoạt .venv):")
    print("       .\\.venv\\Scripts\\activate")
    print("       python src/main.py")
    print("   Cách 2 (Chạy trực tiếp qua Python trong .venv):")
    print("       .\\.venv\\Scripts\\python.exe src/main.py")
    print("   Cách 3 (Dùng uv):")
    print("       uv run python src/main.py\n")
    sys.exit(1)

from src.config import APP_ICON_RELATIVE_PATH, get_resource_path, settings
from src.core.audio_manager import AudioManager
from src.core.background_task_spawner import configure_ted_file_logging, spawn_background_task
from src.core.update_manager import update_manager
from src.bridge.hermes_client_pool import hermes_client_pool
from src.core.app_state_key_value_store import KeyValueStore
from src.core.focus_engine import FocusEngine
from src.core.hotkeys.global_hotkey_manager import hotkey_manager
from src.core.models import db
from src.core.single_instance_guard import acquire_single_instance
from src.modules_runtime.app_runtime_context import AppRuntimeContext
from src.modules_runtime.cheer_line_provider import CheerLineProvider
from src.modules_runtime.module_engine_base_and_factory import ModuleEngineHost
from src.modules_runtime.module_registry_loader import ModuleRegistry
from src.ui.companion_widget import TedCompanionWidget
from src.ui.dashboard_window import DashboardWindow
from src.ui.hotkey_default_action_callbacks_wiring import wire_default_hotkey_actions
from src.ui.pet_speech_bubble_widget import PetSpeechBubble
from src.ui.quick_chat_popup import QuickChatPopup
from src.ui.theme.app_theme_loader import apply_app_theme
from src.ui.tray_manager import TrayManager


def main():
    configure_ted_file_logging(settings.data_dir)
    app = QApplication(sys.argv)
    app.setApplicationName("Ted Companion")
    # Chỉ 1 bản chạy một lúc (2 bản làm đôi số phút app_on); bản thứ hai báo bản đầu hiện nhân vật rồi thoát im lặng
    instance_guard = acquire_single_instance(settings.data_dir)
    if instance_guard is None:
        return
    if sys.platform == "win32":
        # AppUserModelID riêng → taskbar Windows hiện icon Shiba của app thay vì icon python.exe
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TedCompanion.DeepWork")
    # Icon Cún Shiba cho mọi cửa sổ (dashboard, popup, dialog) + taskbar/dock
    app.setWindowIcon(QIcon(str(get_resource_path(APP_ICON_RELATIVE_PATH))))
    app.setQuitOnLastWindowClosed(False)
    apply_app_theme(app)

    # Nạp sẵn bộ vẽ công thức toán ở luồng nền (import matplotlib ~5s) để công thức đầu tiên trong chat hiện ngay
    from src.ui.rich_content.latex_math_image_renderer import warm_up_in_background
    warm_up_in_background()

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    audio_manager = AudioManager()
    if settings.ambient_sound_enabled:
        audio_manager.toggle_ambient(True)

    focus_engine = FocusEngine(audio_manager=audio_manager)

    # Module registry + engine host: engine lỗi/chưa cài chỉ bị bỏ qua, không làm sập app
    from src.core.chat_session_manager import chat_session_manager
    chat_session_manager.set_client_pool(hermes_client_pool)
    registry = ModuleRegistry()
    hermes_client_pool.manifest_connection_resolver = registry.connection_for
    # Module coach (dữ liệu của trẻ) thiếu kết nối → KHÔNG rơi về kết nối đầu tiên (thường là profile công việc)
    hermes_client_pool.strict_module_predicate = lambda mid: getattr(registry.get(mid), "engine", None) != "work"
    ctx = AppRuntimeContext(
        focus_engine=focus_engine, audio=audio_manager, registry=registry, client_pool=hermes_client_pool,
        kv=KeyValueStore(db.engine),
    )
    ctx.quick_chat = QuickChatPopup(focus_engine=focus_engine, client_pool=hermes_client_pool, registry=registry)
    ctx.dashboard = DashboardWindow(focus_engine=focus_engine, registry=registry)
    ctx.dashboard.bind_chat(ctx.quick_chat)   # chat to nằm trong app (trang 💬), không còn popup nổi
    ctx.bubble = PetSpeechBubble(
        focus_engine=focus_engine,
        client_pool=hermes_client_pool,
        registry=registry,
        quick_chat=ctx.quick_chat,
        dashboard=ctx.dashboard,
    )
    ctx.engine_host = ModuleEngineHost(ctx)
    registry.modules_changed.connect(ctx.engine_host.sync)  # nối TRƯỚC dashboard để engine mới có trước khi dựng tab
    ctx.engine_host.sync()
    ctx.dashboard.bind_modules(ctx.engine_host)
    # Gamification Hub: lỗi khởi tạo không được làm sập app (hỏng giữa chừng -> stop Hub, gỡ khóa skin)
    from src.core.gamification.gamification_hub_startup import start_gamification_hub
    start_gamification_hub(ctx, db.engine)
    # Đồng bộ dữ liệu giữa các máy (tắt mặc định): kéo về có dòng mới → dashboard + Hub nạp lại
    from src.core.database_sync.database_sync_controller import database_sync_controller
    database_sync_controller.data_changed.connect(focus_engine.tasks_updated)
    database_sync_controller.start(db.engine)

    def on_about_to_quit():
        database_sync_controller.flush_on_exit()   # đẩy thay đổi cuối lên server (tối đa 10 giây)
        if ctx.gamification is not None:
            ctx.gamification.stop()
        instance_guard.release()   # nhả khóa trước để bản relaunch sau cập nhật không bị tưởng là bản thứ hai
        hotkey_manager.unregister_all()   # trả lại các tổ hợp phím đã đăng ký với OS
        ctx.engine_host.stop_all()
        from src.core.vieneu_sidecar_process_manager import vieneu_sidecar_manager
        vieneu_sidecar_manager.stop()   # tắt sidecar VieNeu-TTS (nếu đang chạy)
        update_manager.trigger_exit_update(relaunch=True)

    app.aboutToQuit.connect(on_about_to_quit)

    cheer_provider = CheerLineProvider(registry, hermes_client_pool, focus_engine=focus_engine, bubble=ctx.bubble)
    companion = TedCompanionWidget(ctx, cheer_provider)
    _tray = TrayManager(
        companion_widget=companion,
        dashboard_window=ctx.dashboard,
        focus_engine=focus_engine,
        audio_manager=audio_manager,
    )
    from src.ui.user_name_dialog import ask_user_name_if_missing
    ask_user_name_if_missing()   # mỗi máy 1 người dùng: hỏi tên 1 lần ("Để sau" → hỏi lại lần mở sau)
    companion.show()
    instance_guard.on_activate = lambda: (companion.show(), companion.raise_())   # bản thứ hai mở -> hiện lại nhân vật

    # Phím tắt toàn cục: nối hành động vào điểm vào có sẵn rồi đăng ký (sau khi companion + tray đã sẵn sàng)
    wire_default_hotkey_actions(ctx, companion, _tray)
    from src.ui.idea_untangle.idea_untangle_feature_wiring import wire_idea_untangle
    wire_idea_untangle(ctx, companion)   # Gỡ Rối Ý Tưởng: hộp thoại + hotkey untangle.open + nudge (trước hotkey_manager.apply)
    try:   # chế độ Họp / Học nhóm (hub phase 13): nghe request_meeting_toggle từ menu/tray/dashboard/hotkey
        from src.ui.meeting_mode.meeting_toggle_coordinator import install_meeting_mode
        install_meeting_mode(ctx, companion)   # coordinator là con của companion → không bị GC
    except Exception:
        logging.getLogger("ted").exception("Không cài được chế độ Họp, tiếp tục không có")
    hotkey_manager.apply(settings.hotkeys)
    try:   # gợi ý sức khỏe nhỏ sau mỗi phiên Deep Work (phase 11); lỗi không được làm sập app
        from src.ui.health_break_prompt_after_focus import install_health_break_prompt
        install_health_break_prompt(ctx, companion)   # controller là con của companion → không bị GC
    except Exception:
        logging.getLogger("ted").exception("Không cài được gợi ý sức khỏe sau Deep Work, tiếp tục không có")
    try:   # Giám sát ứng dụng xao nhãng & đồng hành tập trung trong giờ học
        from src.ui.activity_monitor_wiring import install_activity_monitor
        install_activity_monitor(ctx, companion)
    except Exception:
        logging.getLogger("ted").exception("Không cài được ActivityMonitor, tiếp tục không có")
    try:   # Nhắc nhở ngủ sớm & cảnh báo làm việc muộn
        from src.core.sleep_reminder.sleep_reminder_service import install_sleep_reminder
        install_sleep_reminder(ctx, companion)
    except Exception:
        logging.getLogger("ted").exception("Không cài được nhắc ngủ sớm & làm việc muộn, tiếp tục không có")
    # Kiểm tra bản cập nhật mới trong nền sau 2.5 giây khi mở app
    QTimer.singleShot(
        2500,
        lambda: spawn_background_task(
            update_manager.run_startup_update_flow(ctx.bubble),
            name="startup_update_check",
        ),
    )

    # Giọng Việt là VieNeu → khởi động sẵn sidecar trong nền (sau khi app đã lên) để lần nói đầu không chờ nạp model
    from src.core.vieneu_sidecar_tts_engine import prewarm_vieneu_if_selected
    QTimer.singleShot(15_000, lambda: spawn_background_task(prewarm_vieneu_if_selected(), name="vieneu_prewarm"))

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
