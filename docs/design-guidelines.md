# UI/UX & Design Guidelines

> Nguyên lý thiết kế giao diện, hệ thống Design Tokens và quy chuẩn trải nghiệm người dùng của **Ted Desktop Companion**.

---

## 1. Triết lý thiết kế (Design Philosophy)

Giao diện của Ted được xây dựng dựa trên phong cách **Synthetic Nexus** — sự kết hợp hài hòa giữa nét công nghệ hiện đại, bảng màu tối (Dark Mode) êm dịu bảo vệ mắt khi làm việc ban đêm, và sự sinh động, gần gũi từ thú cưng Chibi ảo.

### Nguyên tắc trải nghiệm cốt lõi
1. **Không gây xao nhãng (Zero Distraction)**: Thú cưng nằm khiêm tốn ở góc màn hình, chỉ xuất hiện bong bóng thoại khi có thông điệp quan trọng hoặc khi người dùng chủ động tương tác.
2. **Phản hồi tức thì & Rõ ràng (Immediate Feedback)**: Mọi thao tác bấm nút, đổi trạng thái Pomodoro hay thăng cấp XP đều đi kèm âm thanh êm dịu và biểu cảm hoạt hình tương ứng.
3. **An toàn & Minh bạch (Safety & Intentionality)**: Mọi hành động có nguy cơ mất mát dữ liệu (như xóa task, reset mục tiêu) đều bắt buộc phải có hộp thoại xác nhận rõ ràng.

---

## 2. Hệ thống màu sắc (Color Palette & Tokens)

Hệ thống token màu sắc được định nghĩa tại `src/ui/theme/design_tokens.py` và triển khai đồng bộ qua QSS:

### 2.1. Màu nền & Bề mặt (Surfaces)
- **Background Primary (`#0D1117`)**: Nền chính của ứng dụng, độ tương phản sâu, giảm mỏi mắt.
- **Surface Secondary (`#161B22`)**: Bề mặt các card, container, bảng điều khiển nội dung.
- **Surface Elevated (`#21262D`)**: Bề mặt các hộp thoại popover, bong bóng thoại, menu chuột phải.
- **Border Default (`#30363D`)**: Đường viền ngăn cách thanh mảnh, tinh tế.

### 2.2. Màu sắc chủ đạo & Điểm nhấn (Accents & Semantics)
- **Primary Brand (`#58A6FF`)**: Màu xanh công nghệ hiện đại, dùng cho các nút hành động chính, tab đang chọn.
- **Focus / Deep Work (`#F0883E`)**: Màu cam ấm tượng trưng cho trạng thái tập trung cao độ và đồng hồ Pomodoro.
- **Success / Completed (`#238636` / `#3FB950`)**: Màu xanh lục dùng cho trạng thái hoàn thành công việc, nhận huy hiệu.
- **Warning / Nudge (`#D29922`)**: Màu vàng hổ phách cảnh báo nhẹ nhàng (sắp đến giờ ngủ, nhắc vận động).
- **Danger (`#DA3633` / `#F85149`)**: Màu đỏ cảnh báo thao tác xóa hoặc ngắt kết nối.

### 2.3. Cấp bậc văn bản (Typography Hierarchy)
- **Text Primary (`#C9D1D9`)**: Chữ sáng rõ nét, dễ đọc trên nền tối.
- **Text Secondary (`#8B949E`)**: Chữ phụ cho các nhãn thời gian, mô tả ngắn, placeholder.
- **Text Muted (`#484F58`)**: Chữ làm mờ cho các thông số kỹ thuật hoặc phím tắt gợi ý.

---

## 3. Quy chuẩn thú cưng & Biểu cảm (Desktop Pet & Moods)

Thú cưng Chibi hỗ trợ các tư thế đồ họa chuẩn (PNG/SVG) tương ứng với từng trạng thái của ứng dụng:

| Trạng thái (Mood / State) | Biểu hiện cử động | Ngữ cảnh kích hoạt |
|---|---|---|
| `idle` | Đứng thư thái, thỉnh thoảng chớp mắt | Trạng thái bình thường ngoài giờ tập trung |
| `focus` | Đeo kính / đội mũ tập trung, chăm chú | Khi đang trong phiên đếm ngược Pomodoro |
| `happy` / `cheer` | Vui mừng, nhảy nhót, tung hoa | Khi hoàn thành 1 phiên Pomodoro, đạt cấp mới |
| `thinking` | Chống cằm, xuất hiện bóng suy nghĩ | Khi đang chờ phản hồi từ AI Agent qua SSE Stream |
| `sleepy` / `sleep` | Ngáp ngủ hoặc cuộn tròn ngủ | Sau 23:00 hoặc khi người dùng không hoạt động lâu |
| `warning` / `alert` | Mở to mắt, giơ bảng nhắc nhở | Khi phát hiện xao nhãng hoặc sắp đến giờ họp |

---

## 4. Quy chuẩn thành phần giao diện (UI Components)

### 4.1. Bong bóng thoại (`PetSpeechBubble`)
- Cửa sổ không viền, nền bán trong suốt (`rgba(33, 38, 45, 0.95)`), bo tròn góc 12px, có bóng đổ mềm (drop shadow).
- Văn bản ngắn gọn, có thể kèm theo link hành động nhanh (ví dụ: `[Bắt đầu làm task này]`, `[Xem ma trận]`).
- Tự động mờ dần và biến mất sau 8 giây nếu người dùng không tương tác.

### 4.2. Hộp thoại Chat nhanh (`QuickChatPopup`)
- Kích thước mặc định 380px x 520px, neo vị trí ngay cạnh thú cưng.
- Hỗ trợ cuộn mượt, render công thức toán học LaTeX bằng hình ảnh sắc nét, bảng dữ liệu Markdown và nút dừng phát biểu (`Stop Reply`).

### 4.3. Nút bấm & Hành động (Buttons)
- **Primary Button**: Nền xanh đậm, chữ trắng, hiệu ứng sáng viền khi hover (`#1F6FEB`).
- **Secondary Button**: Nền tối trong suốt, viền xám mỏng, sáng viền khi di chuột.
- **Destructive Button**: Nền đỏ cảnh báo, luôn mở hộp thoại xác nhận trước khi thực hiện.

### 4.4. Phím tắt toàn cục (Global Hotkeys)
- Hỗ trợ cấu hình lại trong tab Cài đặt:
  - `Ctrl + Alt + T`: Bật / Tắt hiển thị thú cưng.
  - `Ctrl + Alt + F`: Bắt đầu / Tạm dừng phiên Deep Work nhanh.
  - `Ctrl + Alt + C`: Mở nhanh khung chat với Ted.
  - `Ctrl + Alt + M`: Chuyển đổi nhanh chế độ Họp (Meeting Mode).
