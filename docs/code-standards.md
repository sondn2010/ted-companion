# Code Standards & Engineering Guidelines

> Quy chuẩn lập trình, kiến trúc mã nguồn và nguyên tắc an toàn dữ liệu áp dụng cho dự án **Ted Desktop Companion**.

---

## 1. Quy định bắt buộc cốt lõi (Core Inviolable Rules)

### 1.1. An toàn thao tác xóa dữ liệu (Mandatory Deletion Confirmation)
- **Quy tắc bắt buộc:** Bất kỳ thao tác Xóa (Delete) nào trên toàn bộ ứng dụng (Tasks, Rocks, Quiz Items, Calendar Events, History, v.v.) **bắt buộc PHẢI có hộp thoại xác nhận** (`QMessageBox.question`) trước khi thực hiện xóa dữ liệu.
- Tuyệt đối không xóa ngay lập tức khi chưa có sự xác nhận từ người dùng.
- Ví dụ chuẩn trong giao diện PySide6:
  ```python
  from PySide6.QtWidgets import QMessageBox

  reply = QMessageBox.question(
      self,
      "Xác nhận xóa",
      f"Bạn có chắc chắn muốn xóa '{item_title}' không?",
      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
      QMessageBox.StandardButton.No,
  )
  if reply == QMessageBox.StandardButton.Yes:
      self.delete_item(item_id)
  ```

### 1.2. Bảo mật thông tin & Tệp cấu hình nhạy cảm (Security & Secrets)
- Tuyệt đối cấm đọc, in ra console hoặc hiển thị nội dung các tệp:
  - `.env` và các biến thể (`.env.*`, `.env.local`).
  - `applicationsettings.local.json`, `appsettings.local.json`.
  - `applicationsettings.secret.json`, `appsettings.secret.json`, `appsettings.secrets.json`.
- Mọi mật khẩu / khóa bảo mật ngoài máy (ví dụ kết nối PostgreSQL) phải được lưu trữ trong OS Keyring (`keyring` module), không ghi vào `settings.json`.

---

## 2. Quy chuẩn phong cách mã nguồn Python

- **Phiên bản Python**: Yêu cầu tối thiểu Python 3.11+.
- **Type Annotations**: Tất cả các hàm và phương thức mới phải có type hints đầy đủ cho tham số và giá trị trả về (`from typing import Optional, List, Dict`).
- **Pydantic & SQLModel**: Khai báo cấu trúc dữ liệu tường minh; với các cột mở rộng trong database, phải có cơ chế fallback hoặc mặc định an toàn.
- **Tổ chức Import**:
  1. Thư viện chuẩn (Standard Library: `sys`, `os`, `asyncio`, `pathlib`, `logging`).
  2. Thư viện bên thứ ba (Third-party: `PySide6`, `qasync`, `sqlmodel`, `pydantic`).
  3. Mã nguồn nội bộ dự án (`from src.config import ...`, `from src.core... import ...`).
- **Ghi nhật ký (Logging)**:
  - Sử dụng logger chuẩn của dự án:
    ```python
    import logging
    logger = logging.getLogger("ted")
    ```
  - Tránh dùng `print()` trong mã nguồn sản phẩm ngoại trừ kịch bản CLI kiểm tra trước khi khởi chạy.

---

## 3. Quy chuẩn lập trình PySide6 & Bất đồng bộ (Async Qt)

### 3.1. Vòng lặp sự kiện bất đồng bộ với `qasync`
- Ứng dụng chạy trên vòng lặp `qasync.QEventLoop(app)`.
- Khi gọi tác vụ mạng hoặc tính toán dài hạn từ giao diện, sử dụng `asyncio.create_task(...)` hoặc helper `spawn_background_task` để tránh làm đơ giao diện người dùng (UI Freezing).

### 3.2. An toàn luồng (Thread Safety & UI Thread)
- Mọi tương tác cập nhật giao diện (Widget, Label, Dialog, QPainter) **bắt buộc** phải được thực thi trên luồng chính của Qt (Main GUI Thread).
- Tác vụ nền muốn cập nhật UI phải thông qua **Qt Signals & Slots**.

### 3.3. Dọn dẹp tài nguyên & Cửa sổ nổi
- Cửa sổ thú cưng `TedCompanionWidget` sử dụng cờ `Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool`.
- Khi đóng hoặc ẩn ứng dụng, đảm bảo các luồng kiểm tra ngầm (background probe, polling worker) được hủy (cancel) hoặc dừng một cách an toàn.

---

## 4. Quy chuẩn cơ sở dữ liệu (SQLite & Local-First)

1. **Cấu hình SQLite tối ưu**:
   - Chế độ `PRAGMA journal_mode=WAL;`
   - Chế độ `PRAGMA synchronous=NORMAL;`
   - Cấu hình `PRAGMA busy_timeout=5000;` để hạn chế lỗi `database is locked`.
2. **Nâng cấp bảng (Migrations)**:
   - Các cột bổ sung sau này phải đi qua hàm `ensure_columns(...)` trong `src.core.sqlite_add_missing_columns_migration`.
   - Không được thực hiện các lệnh xóa bảng (`DROP TABLE`) trên máy người dùng trong các bản cập nhật.
3. **Mô hình Local-First**:
   - Mọi thao tác CRUD người dùng phải được ghi nhận vào SQLite cục bộ trước khi đồng bộ lên máy chủ đám mây (Cloud PostgreSQL / Hermes AI).

---

## 5. Quy chuẩn viết Unit Test & Kiểm thử

- Mọi module mới phải đi kèm các test case tương ứng trong thư mục `tests/`.
- Sử dụng fixture `qt_offscreen_app_helper` khi cần kiểm thử các widget PySide6 trên môi trường CI/CD không có màn hình hiển thị.
- Đảm bảo `pytest` chạy pass toàn bộ trước khi tạo bản build hoặc xuất xưởng release.
