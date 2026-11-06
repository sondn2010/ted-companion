# Project Overview & PDR (Product Development Requirements)

> **Ted Desktop Companion** — Trợ lý đồng hành Deep Work & Pomodoro trên Desktop (PySide6) kết nối Não AI chuẩn OpenAI-compatible (Local / Cloud / VPS).

---

## 1. Giới thiệu tổng quan (Executive Summary)

**Ted Companion** là ứng dụng desktop native được phát triển bằng Python (PySide6 + qasync) hoạt động theo triết lý **Local-First**, hỗ trợ người dùng duy trì trạng thái tập trung sâu (Deep Work), quản lý công việc theo phương pháp Pomodoro và ma trận Eisenhower, đồng thời tích hợp não bộ AI chuẩn OpenAI-compatible thông qua giao thức FastMCP và SSE Streaming.

Bên cạnh vai trò trợ lý làm việc cho người lớn (`work` engine), Ted còn đóng vai trò là một người bạn học tập đồng hành (`coach` engine) dành cho học sinh, sinh viên với hệ thống thẻ nhớ lặp lại ngắt quãng (Leitner Spaced Repetition), kế hoạch học tập, và báo cáo tiến độ tự động tới phụ huynh qua Telegram.

---

## 2. Đối tượng người dùng & Persona

1. **Knowledge Workers & Software Engineers**
   - Cần không gian làm việc tập trung cao độ, hạn chế xao nhãng.
   - Quản lý công việc bằng Pomodoro, Rocks (mục tiêu quý/tháng), ma trận Eisenhower.
   - Thao tác nhanh qua phím tắt toàn cục (Global Hotkeys) và giao tiếp trực tiếp với AI agent.
2. **Học sinh, Sinh viên (`coach` engine)**
   - Cần lộ trình ôn thi rõ ràng (THCS, Du học, Cao học).
   - Ôn tập kiến thức thông qua Quiz tương tác Spaced Repetition (hộp Leitner 5 cấp).
   - Nhận phản hồi, nộp bài viết luận và theo dõi mốc tiến độ hàng tuần.
3. **Phụ huynh / Mentor**
   - Nhận báo cáo định kỳ về thời gian học, độ tập trung, mức độ xao nhãng qua outbox (Telegram Bot / Webhook).

---

## 3. Mục tiêu sản phẩm (Product Goals & KPIs)

| Mục tiêu | Chi tiết kỹ thuật / Tiêu chí đo lường |
|---|---|
| **Local-First & Zero Latency** | Dữ liệu chính lưu tại SQLite local (`~/.ted/ted_local.db`), WAL mode, hoạt động mượt mà offline không phụ thuộc internet |
| **Nhẹ & Tiết kiệm tài nguyên** | Khởi động nhanh dưới 2s, mức sử dụng RAM tối ưu khi chạy ngầm trên khay hệ thống (System Tray) |
| **Giao diện Sinh động & Thân thiện** | Thú cưng ảo Chibi (Mèo, Shiba, Cú, Gấu trúc,...) cử động trên màn hình, tương tác bằng chuột và bong bóng thoại |
| **Khả năng mở rộng đa module** | Cơ chế Module Registry nạp dynamic từ `modules/<id>/module.yaml` và `~/.ted/modules/` |
| **Bảo vệ sức khỏe & Giấc ngủ** | Nudge vận động nhẹ sau phiên Deep Work, cảnh báo làm việc khuya (Bedtime Alert), nhắc nhở uống nước |
| **Đồng bộ đám mây linh hoạt** | Đồng bộ 2 chiều an toàn SQLite ⇄ PostgreSQL thông qua trigger CDC và API transport |

---

## 4. Phạm vi tính năng (Feature Scope)

### 4.1. Deep Work & Focus Timer
- Đồng hồ Pomodoro đếm ngược hiển thị ngay tại Pet Widget hoặc Dashboard.
- Cấu hình linh hoạt: Thời gian tập trung (mặc định 25 phút), nghỉ ngắn (5 phút), nghỉ dài.
- Mindful Ping định kỳ nhắc nhở quay lại mục tiêu ban đầu nếu xao nhãng.
- Âm thanh môi trường (Ambient Sound) tích hợp sẵn trong ứng dụng.
- Đánh giá chất lượng phiên làm việc (1–5 sao) sau khi hoàn thành.

### 4.2. Quản lý công việc & Ma trận Eisenhower
- Danh mục công việc phân chia theo: `deep_work`, `shallow_work`, `parked_idea` (Parking Lot).
- Phân loại ma trận Eisenhower 4 góc phần tư (Q1: Khẩn cấp & Quan trọng, Q2: Không khẩn cấp nhưng Quan trọng, Q3: Khẩn cấp nhưng Không quan trọng, Q4: Không khẩn cấp & Không quan trọng).
- Sắp xếp thứ tự ưu tiên bằng chỉ số số thực `matrix_order`.
- Ghi chú công việc tự do (`notes`) tự động gộp nội dung từ tính năng Gỡ Rối Ý Tưởng.

### 4.3. Động cơ kép: Work Engine & Coach Engine
- **Work Engine**:
  - Daily Briefing: Tóm tắt lịch trình buổi sáng và kiểm điểm công việc buổi tối.
  - Rocks Management: Quản lý các tảng đá mục tiêu lớn.
  - Lịch họp: Tích hợp và đồng bộ sự kiện lịch, nhắc nhở trước giờ họp.
- **Coach Engine**:
  - Hộp Leitner (Spaced Repetition System) với 5 cấp độ nhớ, tính toán thời gian đến hạn ôn tập.
  - Tự động phân phối câu hỏi trắc nghiệm / tự luận.
  - Nộp bài viết và chấm điểm phản hồi qua AI.
  - Gửi báo cáo tiến độ học tập (Progress Report Outbox).

### 4.4. Trợ lý giọng nói (TTS & STT)
- **TTS (Text-to-Speech)**:
  - Hỗ trợ server OpenAI-compatible `/v1/audio/speech`.
  - Hỗ trợ mô hình nội bộ VieNeu-TTS chạy qua sidecar process độc lập trên local.
  - Cơ chế Gapless PCM Streaming và Chunk playback giúp âm thanh phát mượt mà không độ trễ.
- **STT (Speech-to-Text)**:
  - Nhập liệu câu hỏi qua microphone với giao thức `/v1/audio/transcriptions` hoặc binary `whisper.cpp` cục bộ.

### 4.5. Gamification & Hub phát triển cá nhân
- Sổ cái kinh nghiệm (`XpLedger`): Cộng XP khi hoàn thành phiên tập trung, làm bài kiểm tra, duy trì streak.
- Cấp độ nhân vật: Thăng hạng cấp độ từ Cún sơ sinh đến Bậc thầy Deep Work.
- Bộ huy hiệu thành tích (Badges): Mở khóa theo tuần, theo số phiên tập trung và streak liên tục.
- Bộ sưu tập skin có thể mở khóa (Unlockable Skin Packs) dựa trên chuỗi thành tích.

### 4.6. Cầu nối AI Não bộ & FastMCP Server
- Cầu nối OpenAI Client Pool hỗ trợ đa kết nối (Work profile & Coach profile riêng biệt).
- Phân tích cú pháp thẻ cảm xúc thời gian thực `<mood:tag>` để điều khiển biểu cảm thú cưng.
- Tích hợp máy chủ FastMCP (`ted-companion-tools`) cho phép các mô hình AI điều khiển trực tiếp UI qua IPC queue.

---

## 5. Yêu cầu phi chức năng (Non-Functional Requirements)

1. **Độ ổn định & Single Instance Guard**: Đảm bảo tại một thời điểm chỉ có duy nhất một tiến trình Ted Companion chạy trên máy, tránh xung đột file DB và lock socket.
2. **Khả năng tương thích nền tảng**: Hoạt động tối ưu trên Windows 10/11 (hỗ trợ taskbar AppUserModelID riêng) và macOS.
3. **An toàn dữ liệu & Bảo mật**: Mật khẩu và token kết nối cơ sở dữ liệu PostgreSQL được lưu trữ an toàn trong Windows Credential Manager / macOS Keychain thông qua thư viện `keyring`.
4. **Cơ chế tự phục hồi (Fault Tolerance)**: Khi mất kết nối mạng hoặc server AI ngoại tuyến, ứng dụng chuyển sang chế độ backoff probe im lặng, không làm đơ giao diện người dùng.
