# Project Roadmap

> Lộ trình phát triển sản phẩm, các mốc nâng cấp kỹ thuật và kế hoạch dài hạn của **Ted Desktop Companion**.

---

## 1. Các cột mốc đã hoàn thành (Achieved Milestones — v1.0.0 đến v1.5.1)

- [x] **v1.0.0: Nền tảng Pomodoro & Desktop Pet**
  - Ra mắt cửa sổ thú cưng Chibi ảo (Mèo, Shiba, Cú, Gấu trúc).
  - Đồng hồ đếm ngược Pomodoro và quản lý task cục bộ.
- [x] **v1.2.0: Cầu nối AI & Giao thức FastMCP**
  - Tích hợp cầu nối AI Client với tính năng SSE Streaming.
  - Phân tích cú pháp thẻ tâm trạng `<mood:tag>` để đổi biểu cảm thú cưng theo ngữ cảnh thoại.
  - Xây dựng FastMCP Server cho phép các AI Agent bên ngoài điều khiển ứng dụng qua hàng đợi IPC.
- [x] **v1.3.0: Động cơ kép Work & Coach Modules**
  - Kiến trúc nạp module động qua `module.yaml`.
  - Triển khai `work` engine: Quản lý Rocks, Ma trận Eisenhower, Lịch làm việc và Daily Briefing.
  - Triển khai `coach` engine: Thuật toán Spaced Repetition (hộp Leitner 5 cấp), hệ thống trắc nghiệm/tự luận, gửi báo cáo tiến độ học tập ra Telegram.
- [x] **v1.4.0: Giọng nói Offline & VieNeu-TTS Sidecar**
  - Quản lý tiến trình phụ VieNeu-TTS chạy cục bộ tối ưu cho Tiếng Việt.
  - Trình phát âm thanh PCM không độ trễ (Gapless PCM Stream Player) và nhận dạng giọng nói qua mic.
- [x] **v1.5.1: Đồng bộ đám mây & Giám sát thông minh (Current Release)**
  - Cơ chế đồng bộ SQLite ⇄ PostgreSQL hai chiều an toàn với CDC Triggers.
  - Hệ thống giám sát ứng dụng học tập/làm việc (`ActivityWatcher`) và phát hiện xao nhãng.
  - Chế độ họp (`MeetingMode`) và gợi ý vận động nhẹ bảo vệ sức khỏe sau phiên Deep Work.

---

## 2. Kế hoạch phát triển ngắn hạn (Near-Term — Quý 1-2)

### 2.1. Nâng cao trải nghiệm người dùng & Tối ưu hiệu năng
- [ ] **Tối ưu bộ nhớ**: Giảm thêm 30% mức tiêu thụ RAM của tiến trình PySide6 khi ứng dụng chạy ở chế độ thu nhỏ vào System Tray.
- [ ] **Cải thiện khởi động**: Nạp trước (lazy-load/warm-up) các thư viện đồ họa nặng (matplotlib, sounddevice) để giảm thời gian khởi chạy xuống dưới 1.5 giây.
- [ ] **Giao diện kéo thả nâng cao**: Hoàn thiện tính năng kéo thả mượt mà các thẻ công việc giữa các góc phần tư của ma trận Eisenhower.

### 2.2. Mở rộng tính năng học tập & Huấn luyện (Coach Expansion)
- [ ] **Ngân hàng đề thi đa định dạng**: Hỗ trợ nhập trực tiếp đề thi trắc nghiệm từ file Word (`.docx`), Excel (`.xlsx`) hoặc Markdown.
- [ ] **Phân tích chiều sâu kết quả thi**: Biểu đồ hóa ma trận điểm yếu của học sinh theo từng chuyên đề kiến thức để AI tự động lên lịch ôn tập bù.

---

## 3. Kế hoạch phát triển trung hạn (Medium-Term — Quý 3-4)

### 3.1. Trợ lý đa phương thức (Multimodal Companion)
- [ ] **Hỗ trợ thị giác máy tính cục bộ (Local OCR)**: Cho phép kéo ảnh bài tập hoặc tài liệu trực tiếp vào thú cưng để AI đọc và tạo thẻ ôn tập tức thì.
- [ ] **Tương tác cử chỉ & Bàn phím không chạm**: Nhận diện cử chỉ tay đơn giản qua webcam để bắt đầu / tạm dừng phiên Pomodoro.

### 3.2. Mở rộng hệ sinh thái & Phân phối
- [ ] **Đóng gói đa nền tảng hoàn thiện**: Cung cấp bộ cài tự động `.msi` / `.exe` có ký số (Code Signing) trên Windows và file `.dmg` / notarized trên macOS.
- [ ] **Cổng chợ tiện ích mở rộng (Community Module Hub)**: Cho phép người dùng tải và chia sẻ các gói nhân vật Chibi và các module học tập do cộng đồng đóng góp.

---

## 4. Kế hoạch dài hạn (Long-Term Vision)

- [ ] **Hệ điều hành tập trung cá nhân (Autonomous Focus Operating Layer)**: Ted không chỉ theo dõi mà còn chủ động điều tiết môi trường số của người dùng (tự động bật chế độ Do Not Disturb trên máy tính, chặn các trang web gây xao nhãng trong phiên làm việc sâu).
- [ ] **Bộ nhớ ngữ cảnh dài hạn (Episodic Memory)**: Ted ghi nhớ thói quen, nhịp sinh học và phong cách làm việc của từng người dùng để đưa ra lời khuyên cá nhân hóa tối ưu nhất.
