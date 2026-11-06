# 🐾 Ted Companion

<div align="center">

![Ted Companion](assets/icons/app_icon.png)

**Trợ lý đồng hành Deep Work & Pomodoro trên Desktop (PySide6) kết nối Não AI chuẩn OpenAI-compatible (Local / Cloud / VPS)**

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt6-green.svg)](https://wiki.qt.io/Qt_for_Python)
[![Protocol](https://img.shields.io/badge/AI-FastMCP%20%26%20SSE-orange.svg)](https://modelcontextprotocol.io/)
[![Storage](https://img.shields.io/badge/Storage-SQLite%20(Local--First)-yellow.svg)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg)](LICENSE)

</div>

---

## 🌟 Điểm nổi bật (Key Features)

- **🐾 Chibi Desktop Companion**: Thú cưng ảo luôn nổi trên màn hình (Mèo Ted, Cún Shiba, Cú Đêm, Gấu Trúc...) với các trạng thái cử động linh hoạt (Tập trung, Nghỉ ngơi, Cổ vũ, Buồn ngủ).
- **⏱️ Deep Work & Pomodoro Engine**: Quản lý phiên làm việc sâu 25/5 phút, đếm số lần xao nhãng, nhắc nhở chánh niệm (Mindful Ping), và tích hợp sẵn âm thanh môi trường (Ambient Sound).
- **🎯 Ma trận Eisenhower & Quản lý công việc**: Phân loại 4 góc phần tư ưu tiên, sắp xếp linh hoạt, đồng thời cung cấp "Parking Lot" cất giữ nhanh các ý tưởng xao nhãng nảy sinh trong lúc làm việc.
- **🔄 Động cơ kép (Dual Engines)**:
  - **Work Engine**: Báo cáo ngày (Daily Briefing), theo dõi mục tiêu lớn (Rocks), đồng bộ lịch làm việc và nhắc nhở cuộc họp.
  - **Coach Engine**: Trợ lý học tập cá nhân với thuật toán Lặp lại ngắt quãng (Leitner 5 hộp nhớ), ngân hàng câu hỏi trắc nghiệm/tự luận và tự động gửi báo cáo tiến độ học tập qua Telegram.
- **🧠 Cầu nối Não bộ AI (OpenAI Compatible & FastMCP)**:
  - Tích hợp OpenAI Client Pool hỗ trợ SSE Streaming phản hồi siêu tốc, tương thích OpenAI, Ollama, vLLM, LM Studio, v.v.
  - Tự động bóc tách thẻ cảm xúc `<mood:tag>` để đổi biểu cảm thú cưng theo thời gian thực.
  - Tích hợp sẵn máy chủ **FastMCP** (`ted-mcp`), cho phép Claude Desktop, Cursor, hay Agent bên ngoài điều khiển giao diện Ted qua IPC an toàn.
- **🎙️ Trợ lý giọng nói đa chế độ (TTS & STT)**:
  - **Text-to-Speech**: Hỗ trợ server OpenAI-compatible và mô hình cục bộ VieNeu-TTS chạy ngầm không độ trễ.
  - **Speech-to-Text**: Nhập liệu qua micro với Whisper server hoặc binary `whisper.cpp` offline.
- **🎮 Gamification & Sức khỏe cá nhân**:
  - Hệ thống điểm kinh nghiệm XP, thăng hạng cấp độ, chuỗi ngày liên tục (streak) và bộ sưu tập huy hiệu tuần.
  - Cảnh báo làm việc khuya (Bedtime Alert) và gợi ý vận động nhẹ sau mỗi phiên Deep Work.
- **💾 Local-First & Đồng bộ đám mây**:
  - Cơ sở dữ liệu SQLite cục bộ (WAL Mode), mở là chạy ngay lập tức, không phụ thuộc vào internet.
  - Tùy chọn đồng bộ 2 chiều bảo mật với cơ sở dữ liệu PostgreSQL từ xa.

---

## 🚀 Bắt đầu nhanh (Quick Start)

### Yêu cầu hệ thống
- Hệ điều hành: Windows 10/11 hoặc macOS Monterey (12.0)+
- Python: 3.11 trở lên (khuyên dùng 3.11 hoặc 3.12)
- Trình quản lý gói: `uv` (khuyên dùng) hoặc `pip`

### 1. Cài đặt môi trường
```bash
# Clone kho mã nguồn
git clone <repository_url> ted-companion
cd ted-companion

# Tạo và kích hoạt môi trường ảo (ví dụ với uv)
uv venv
.venv\Scripts\activate.bat   # Trên Windows CMD
# Hoặc: .venv\Scripts\Activate.ps1 trên PowerShell
# Hoặc: source .venv/bin/activate trên macOS/Linux

# Cài đặt thư viện phụ thuộc
uv pip install -r requirements.txt
uv pip install pyinstaller pytest pytest-asyncio
```

### 2. Thiết lập cấu hình
Sao chép file cấu hình mẫu `.env.example`:
```bash
copy .env.example .env
```
*(Tùy chỉnh thông số kết nối AI, cổng máy chủ giọng nói và giao diện theo nhu cầu).*

### 3. Khởi chạy ứng dụng
```bash
# Khởi chạy qua kịch bản có sẵn
run.bat

# Hoặc chạy trực tiếp bằng python
python src/main.py
```

---

## 🤖 Kết nối với AI qua FastMCP (Model Context Protocol)

Ted tích hợp sẵn FastMCP server cho phép các trợ lý như Claude Desktop hoặc Cursor điều khiển trực tiếp Ted:

```bash
# Khởi chạy MCP Server
python src/bridge/ted_mcp_server.py
```

Thêm cấu hình vào `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "ted-companion": {
      "command": "python",
      "args": ["<đường_dẫn_tuyệt_đối>/src/bridge/ted_mcp_server.py"]
    }
  }
}
```

**Các tools AI được cung cấp:**
- `get_today_focus_summary()`: Lấy số liệu thống kê phiên làm việc sâu và task trong ngày.
- `create_or_schedule_task(title, estimated_pomodoros, category)`: Tạo việc mới hoặc lưu ý tưởng vào Parking Lot.
- `control_pomodoro(action, task_title, duration_minutes)`: Bắt đầu, tạm dừng hoặc dừng đồng hồ đếm ngược.
- `change_character_skin(skin_name)`: Đổi ngoại hình thú cưng Chibi.

---

## ⌨️ Phím tắt toàn cục mặc định (Default Hotkeys)

| Phím tắt | Chức năng |
|---|---|
| `Ctrl + Alt + T` | Ẩn / Hiện nhân vật thú cưng trên màn hình |
| `Ctrl + Alt + F` | Bắt đầu / Tạm dừng nhanh phiên Deep Work |
| `Ctrl + Alt + C` | Mở nhanh cửa sổ trò chuyện với Ted |
| `Ctrl + Alt + M` | Bật / Tắt chế độ Cuộc họp (Meeting Mode) |

*(Bạn có thể thay đổi các phím tắt này trong tab **Cài đặt** của ứng dụng).*

---

## 📦 Đóng gói & Phát hành (Build & Packaging)

### Đóng gói ứng dụng thành file `.exe` độc lập trên Windows:
```cmd
scripts\build_windows.bat
```
File thực thi độc lập sẽ được sinh ra tại: `dist\TedCompanion.exe`.

### Quy trình phát hành phiên bản mới (Release):
```cmd
release.bat
```

---

## 📁 Cấu trúc thư mục (Project Structure)

```
ted-companion/
├── assets/             # Âm thanh, biểu tượng, ảnh thú cưng, font chữ
├── docs/               # Tài liệu thiết kế, kiến trúc và hướng dẫn kỹ thuật
├── modules/            # Các module nghiệp vụ (work, caohoc, duhoc, thcs)
├── scripts/            # Kịch bản đóng gói build .exe, sinh assets và release
├── src/
│   ├── bridge/         # Cầu nối Não AI (OpenAI-compatible), bộ lọc tâm trạng và FastMCP Server
│   ├── core/           # Quản lý Pomodoro, CSDL SQLite, Gamification, Audio, Voice
│   ├── engines/        # Động cơ nghiệp vụ: Work Engine & Coach Engine
│   ├── modules_runtime/# Nạp động và quản lý vòng đời module
│   └── ui/             # Giao diện PySide6 (Pet Widget, Dashboard, Chat, Theme)
├── tests/              # Hơn 130+ test cases tự động (pytest)
├── pyproject.toml      # Khai báo cấu hình dự án & dependencies
└── requirements.txt    # Danh sách thư viện pip
```

---

## 📚 Tài liệu chi tiết (Documentation)

Hệ thống tài liệu hoàn chỉnh được lưu trữ tại thư mục [`docs/`](docs/):

- 📋 [Tổng quan sản phẩm & Yêu cầu (PDR)](docs/project-overview-pdr.md)
- 🏗️ [Kiến trúc hệ thống (System Architecture)](docs/system-architecture.md)
- 📊 [Tóm tắt mã nguồn & Cấu trúc thư mục (Codebase Summary)](docs/codebase-summary.md)
- 📐 [Quy chuẩn lập trình & Nguyên tắc an toàn dữ liệu (Code Standards)](docs/code-standards.md)
- 🚀 [Hướng dẫn cài đặt & Đóng gói (Deployment Guide)](docs/deployment-guide.md)
- 🎨 [Nguyên tắc thiết kế UI/UX & Design Tokens](docs/design-guidelines.md)
- 🗺️ [Lộ trình phát triển sản phẩm (Project Roadmap)](docs/project-roadmap.md)

---

## 📄 Bản quyền (License)

Dự án được phân phối dưới giấy phép [GNU General Public License v3.0](LICENSE).
