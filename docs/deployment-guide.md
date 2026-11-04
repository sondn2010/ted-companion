# Deployment & Operations Guide

> Hướng dẫn cài đặt môi trường phát triển, cấu hình hệ thống, đóng gói ứng dụng bằng PyInstaller và phát hành bản phát hành mới cho **Ted Desktop Companion**.

---

## 1. Yêu cầu hệ thống (System Prerequisites)

- **Hệ điều hành**:
  - Windows 10/11 64-bit (được tối ưu hóa giao diện và phím tắt hệ thống).
  - macOS Monterey (12.0) trở lên.
- **Python**: Phiên bản 3.11 trở lên (khuyên dùng Python 3.11 hoặc 3.12).
- **Trình quản lý gói**: Hỗ trợ chuẩn `uv` hoặc `pip` kèm `virtualenv`.
- **Cấu hình phần cứng tối thiểu**:
  - CPU: 2 nhân x86_64 hoặc Apple Silicon.
  - RAM: Tối thiểu 4 GB (khuyên dùng 8 GB nếu chạy kèm giọng nói cục bộ).
  - Dung lượng ổ cứng trống: 500 MB (thêm 1 GB nếu tải mô hình nhận diện giọng nói).

---

## 2. Thiết lập môi trường phát triển (Local Development Setup)

### Bước 1: Clone kho mã nguồn và điều hướng vào thư mục
```bash
git clone <repository_url> ted-companion
cd ted-companion
```

### Bước 2: Tạo và kích hoạt môi trường ảo
Sử dụng `uv` (nhanh nhất):
```bash
uv venv
# Trên Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Hoặc Command Prompt:
.venv\Scripts\activate.bat
```
Hoặc dùng Python venv truyền thống:
```bash
python -m venv .venv
.venv\Scripts\activate.bat
```

### Bước 3: Cài đặt các gói phụ thuộc
```bash
uv pip install -r requirements.txt
# Cài đặt thêm các gói phục vụ kiểm thử và đóng gói:
uv pip install pyinstaller pytest pytest-asyncio
```

### Bước 4: Cấu hình tệp môi trường
Sao chép tệp mẫu `.env.example` thành `.env`:
```bash
# Trên Windows (PowerShell / Command Prompt):
copy .env.example .env
```
> **Lưu ý**: Tệp `.env` chứa các tùy chỉnh cục bộ trên máy của bạn và đã được cấu hình trong `.gitignore` để không bao giờ bị đưa lên kho mã nguồn.

### Bước 5: Khởi chạy ứng dụng
Có thể chạy bằng các tệp lệnh tiện ích có sẵn:
```bash
# Cách 1: Sử dụng file batch có sẵn
run.bat

# Cách 2: Khởi chạy trực tiếp từ dòng lệnh
python src/main.py

# Cách 3: Khởi chạy qua uv
uv run python src/main.py
```

---

## 3. Khởi chạy máy chủ FastMCP (Ted MCP Server)

Ted tích hợp sẵn FastMCP server để kết nối với các công cụ phát triển như Claude Desktop, Cursor hoặc Hermes Agent:
```bash
# Khởi chạy máy chủ FastMCP độc lập
python src/bridge/ted_mcp_server.py

# Hoặc qua CLI entry point (nếu đã cài đặt dạng package):
ted-mcp
```

Cấu hình trong file cấu hình MCP của client (ví dụ `claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "ted-companion": {
      "command": "python",
      "args": ["D:/Sources/fish/77.product/ted-companion/src/bridge/ted_mcp_server.py"]
    }
  }
}
```

---

## 4. Quy trình đóng gói bản cài đặt (Packaging with PyInstaller)

Ứng dụng sử dụng cấu hình tùy biến cao trong tệp `TedCompanion.spec` để gom toàn bộ assets, module YAML, template prompt và dynamic imports. Bộ cài tạo ra là tệp thực thi duy nhất (Single Standalone Executable) không chứa sẵn các mô hình giọng nói nặng nhằm giảm thiểu dung lượng tải về.

### 4.1. Đóng gói trên Windows
Chạy script tự động:
```cmd
scripts\build_windows.bat
```
Hoặc chạy lệnh PyInstaller thủ công:
```cmd
python -m PyInstaller --clean --noconfirm TedCompanion.spec
```
Kết quả file thực thi sẽ được xuất tại thư mục: `dist\TedCompanion.exe`.

### 4.2. Đóng gói trên macOS
Chạy kịch bản bash shell:
```bash
bash scripts/build_macos.sh
```
Kết quả ứng dụng sẽ được lưu tại thư mục: `dist/TedCompanion.app`.

---

## 5. Quy trình phát hành phiên bản mới (Release Workflow)

Dự án cung cấp kịch bản tự động hóa quy trình cập nhật phiên bản, đóng gói và tải lên kho phân phối:
```cmd
# Chạy script release tương tác
release.bat

# Hoặc truyền trực tiếp số phiên bản mục tiêu:
python scripts\publish_release.py 1.5.2
```

Quy trình tự động thực hiện:
1. Xác thực cú pháp và cập nhật `APP_VERSION` trong `src/core/version_config.py`.
2. Kiểm tra tính toàn vẹn của toàn bộ manifest trong thư mục `modules/`.
3. Đóng gói ứng dụng qua PyInstaller.
4. Tính mã băm SHA256 của file binary và cập nhật tệp kê khai `version.json`.
5. Tạo thẻ phát hành (Git Tag) và đồng bộ tệp lên hệ thống CDN phân phối.

---

## 6. Vị trí lưu trữ dữ liệu người dùng (User Data & Storage)

Toàn bộ dữ liệu của ứng dụng được lưu trữ riêng biệt tại thư mục người dùng:
- Đường dẫn mặc định: `~/.ted/` (hoặc biến môi trường `TED_HOME`).
- Tệp cơ sở dữ liệu chính: `~/.ted/ted_local.db` (SQLite).
- Tệp cấu hình người dùng: `~/.ted/settings.json`.
- Thư mục mô hình giọng nói tải về: `~/.ted/voice_models/`.
- Thư mục nhật ký (Logs): `~/.ted/logs/ted.log`.
