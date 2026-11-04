# Codebase Summary

> Báo cáo cấu trúc tổng thể, tổ chức thư mục và thống kê mã nguồn của dự án **Ted Desktop Companion**.

---

## 1. Thống kê quy mô mã nguồn

Dự án gồm hơn **320 file mã nguồn Python** với khoảng **~30,000 dòng lệnh (LOC)**, được tổ chức thành các tầng kiến trúc rõ ràng:

| Phân hệ / Thư mục | Số lượng File Python | Số dòng lệnh (LOC ước tính) | Chức năng chính |
|---|---|---|---|
| `src/core/` | 143 | ~12,200 | Lõi logic: Models, DB SQLite/PG, Gamification, Audio, Hotkeys, Watcher, Untangle, Settings |
| `src/ui/` | 107 | ~12,600 | Giao diện người dùng PySide6: Pet Widget, Dashboard, Quick Chat, Theme, Rich Content Renderers |
| `src/engines/` | 59 | ~3,500 | Bộ xử lý nghiệp vụ chuyên biệt: `work` (Rocks, Briefing, Calendar) & `coach` (Leitner, Quiz, Reports) |
| `src/bridge/` | 9 | ~580 | Cầu nối Hermes AI Agent (SSE Client, Pool, Mood Parser) & FastMCP Server (`ted-mcp`) |
| `src/modules_runtime/` | 8 | ~390 | Hệ thống nạp runtime module, manifest validation, schema, template prompts |
| `modules/` | Config + Prompts | ~500 | Các module cài sẵn: `work`, `caohoc`, `duhoc`, `thcs` |
| `scripts/` | 9 | ~1,200 | Scripts đóng gói PyInstaller, phát hành release, sinh ảnh badge, quản lý character packs |
| `tests/` | 130+ files | ~15,000 | Bộ kiểm thử tự động toàn diện sử dụng pytest & pytest-asyncio |

---

## 2. Bản đồ cấu trúc thư mục (Directory Tree)

```
ted-companion/
├── assets/                          # Tài nguyên đồ họa, âm thanh, phông chữ
│   ├── animations/                  # Ảnh trạng thái cử động của thú cưng
│   ├── badges/                      # Huy hiệu thành tích gamification
│   ├── character_pack/              # Bộ nhân vật Chibi đóng gói lúc build
│   ├── fonts/                       # Phông chữ tùy biến
│   ├── icons/                       # Icon ứng dụng (app_icon.png, shiba,...)
│   ├── sounds/                      # Âm thanh thông báo, nhạc nền ambient
│   └── unlockable_skin_packs/       # Các gói trang phục mở khóa theo cấp độ
├── modules/                         # Định nghĩa các module nghiệp vụ
│   ├── caohoc/                      # Module Ôn thi Cao học
│   ├── duhoc/                       # Module Lộ trình Du học
│   ├── thcs/                        # Module Học tập bậc THCS
│   ├── work/                        # Module Công việc chuẩn (Briefing, Calendar, Rocks)
│   └── README.md
├── scripts/                         # Bộ công cụ build & deployment
│   ├── build_macos.sh               # Đóng gói ứng dụng cho macOS
│   ├── build_windows.bat            # Đóng gói ứng dụng .exe cho Windows
│   ├── generate_badge_images.py     # Tự động render ảnh huy hiệu
│   ├── install_character_pack.py    # Script cài đặt gói nhân vật
│   ├── install_unlockable_skin_packs.py # Script nạp skin mở khóa
│   └── publish_release.py           # Tự động hóa tạo bản release GitHub
├── src/                             # Mã nguồn chính của ứng dụng
│   ├── config.py                    # Quản lý AppConfig (Settings schema v2, đường dẫn, env)
│   ├── main.py                      # Điểm vào chính của ứng dụng PySide6 (main entry point)
│   ├── bridge/                      # Cầu nối AI và máy chủ MCP
│   │   ├── chat_json_tail_detector.py # Nhận diện JSON contract gửi kèm ở đuôi câu trả lời AI
│   │   ├── hermes_client.py         # Client gọi AI backend qua HTTP/SSE Streaming
│   │   ├── hermes_client_pool.py    # Quản lý pool kết nối nhiều profile AI
│   │   ├── hermes_mood_tag_stream_parser.py # Bóc tách thẻ <mood:tag> điều khiển biểu cảm
│   │   ├── hermes_offline_probe_and_backoff.py # Thăm dò trạng thái kết nối AI có backoff
│   │   ├── sync_worker.py           # Worker đồng bộ dữ liệu ngầm lên AI server
│   │   └── ted_mcp_server.py        # FastMCP Server cung cấp tools cho AI agents
│   ├── core/                        # Logic nền tảng và cơ sở dữ liệu
│   │   ├── activity_watcher/        # Giám sát ứng dụng đang mở, phát hiện xao nhãng
│   │   ├── database_sync/           # Đồng bộ dữ liệu SQLite ⇄ PostgreSQL an toàn
│   │   ├── gamification/            # Sổ cái XP, tính toán thăng cấp, chuỗi streak, huy hiệu
│   │   ├── hotkeys/                 # Trình quản lý phím tắt toàn cục (Global Hotkey Manager)
│   │   ├── idea_untangle/           # Trợ lý Gỡ Rối Ý Tưởng khi người dùng bị bế tắc
│   │   ├── meeting_mode/            # Chế độ họp: Theo dõi thời lượng và nén âm thanh
│   │   ├── sleep_reminder/          # Nhắc nhở đi ngủ đúng giờ và cảnh báo làm việc khuya
│   │   ├── vieneu_sidecar/          # Tiến trình con chạy mô hình Text-to-Speech VieNeu
│   │   ├── app_state_key_value_store.py # Bảng key-value lưu trạng thái runtime
│   │   ├── audio_manager.py         # Phát âm thanh click, ding, ambient background
│   │   ├── focus_engine.py          # Động cơ Pomodoro đếm ngược và quản lý trạng thái tập trung
│   │   ├── i18n.py                  # Đa ngôn ngữ (Tiếng Việt / English)
│   │   ├── models.py                # Database Manager và các SQLModel tables
│   │   ├── single_instance_guard.py # Đảm bảo chỉ 1 ứng dụng Ted chạy trên hệ thống
│   │   ├── stt_service.py           # Dịch vụ nhận diện giọng nói Speech-to-Text
│   │   ├── tts_service.py           # Dịch vụ đọc văn bản Text-to-Speech
│   │   └── update_manager.py        # Tự động kiểm tra và cập nhật ứng dụng
│   ├── engines/                     # Động cơ nghiệp vụ riêng cho từng phân hệ
│   │   ├── work/                    # Nghiệp vụ công việc: Rocks, Calendar, Eisenhower
│   │   └── coach/                   # Nghiệp vụ học tập: Spaced Repetition, Quiz, Writing
│   ├── modules_runtime/             # Runtime quản lý vòng đời module
│   │   ├── app_runtime_context.py   # Context dùng chung truyền vào các engine
│   │   ├── cheer_line_provider.py   # Cung cấp câu động viên ngẫu nhiên theo ngữ cảnh
│   │   ├── module_manifest_schema.py# Định dạng hợp lệ của `module.yaml`
│   │   └── module_registry_loader.py# Quét và nạp các module hợp lệ
│   └── ui/                          # Toàn bộ giao diện PySide6
│       ├── dashboard_tabs/          # Các tab con trong cửa sổ Dashboard chính
│       ├── module_tabs/             # Các tab động được sinh ra từ module cài đặt
│       ├── rich_content/            # Render công thức toán LaTeX (matplotlib), SVG, HTML
│       ├── theme/                   # Theme Synthetic Nexus (QSS, Design Tokens, Colors)
│       ├── companion_widget.py      # Cửa sổ thú cưng trôi nổi trên màn hình (Desktop Pet)
│       ├── dashboard_window.py      # Cửa sổ Dashboard tổng quan với thanh điều hướng bên
│       ├── pet_speech_bubble_widget.py # Bong bóng hội thoại hiển thị lời nhắc
│       ├── quick_chat_popup.py      # Hộp thoại chat nhanh trôi nổi cạnh thú cưng
│       └── tray_manager.py          # Quản lý biểu tượng trên khay hệ thống (System Tray)
├── tests/                           # Toàn bộ test case tự động hóa (pytest)
├── pyproject.toml                   # Cấu hình dự án và dependencies
├── requirements.txt                 # File requirements cho pip / build script
├── TedCompanion.spec                # Cấu hình PyInstaller cho Windows/macOS
└── README.md                        # Tài liệu hướng dẫn bắt đầu nhanh
```

---

## 3. Các thực thể dữ liệu chính (Data Models)

Hệ thống sử dụng **SQLModel** (kết hợp Pydantic và SQLAlchemy) lưu trữ trên SQLite local (`~/.ted/ted_local.db`):

1. **`Task`**:
   - `id`, `title`, `category` (`deep_work`, `shallow_work`, `parked_idea`), `estimated_pomodoros`, `completed_pomodoros`, `status` (`todo`, `in_progress`, `done`, `archived`), `scheduled_date`, `quadrant` (Eisenhower 1..4), `matrix_order`, `notes`.
2. **`FocusSession`**:
   - `id`, `task_id`, `intent_statement`, `planned_minutes`, `actual_minutes`, `distraction_count`, `focus_rating` (1..5), `started_at`, `ended_at`.
3. **`DailyJournal`**:
   - `date`, `morning_intention`, `evening_reflection`, `ai_summary`, `mood_tag`.
4. **`XpLedger` & `WeeklySnapshot`**:
   - Ghi nhận lịch sử nhận điểm kinh nghiệm theo thời gian thực và chốt dữ liệu xếp hạng mỗi tuần.
5. **`QuizItem`, `ReviewState`, `Attempt`**:
   - Lưu trữ ngân hàng câu hỏi, trạng thái hộp Leitner và lịch sử làm bài kiểm tra.
6. **`Rock`**:
   - Quản lý các mục tiêu trung và dài hạn của người dùng.
7. **`ActivityLog` & `MeetingSession`**:
   - Lưu trữ dữ liệu ứng dụng hoạt động trên máy tính và các phiên họp.
