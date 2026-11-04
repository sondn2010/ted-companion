# Ted modules

Mỗi module = 1 thư mục `modules/<id>/module.yaml`. Ted quét thư mục built-in (đóng gói trong exe, chỉ đọc) rồi `~/.ted/modules/` (cùng id thì thư mục người dùng thắng). Module sai schema bị bỏ qua và lỗi hiện trong Settings.

## Manifest schema (khoá lạ bị từ chối)
| Khoá | Ghi chú |
|---|---|
| `id` | slug `[a-z0-9_-]{1,32}` |
| `name`, `icon` | hiển thị |
| `engine` | `work` hoặc `coach` |
| `connection` | id trong `connections` (có thể bị override trong Settings) |
| `enabled` | mặc định `false`; Settings `modules.<id>.enabled` ghi đè |
| `order` | thứ tự tab/menu (nhỏ trước) |
| `learner_id` | bắt buộc với `coach`, slug (đi vào đường dẫn file trên server) |
| `prompts`, `settings` | chỉ `work`; `coach` KHÔNG được khai báo |

Prompt md dùng `{{var}}` (biến không biết được giữ nguyên, dấu `{ }` của JSON an toàn). Đường dẫn prompt phải nằm trong thư mục module.

## Menu cố định theo engine
- `work`: Công việc hôm nay · Hỏi Ted · Rocks · Lịch họp
- `coach`: Hôm nay · Ôn ngay · Hỏi · Tiến độ & mốc · Đồng bộ kế hoạch

(định nghĩa trong `src/modules_runtime/engine_fixed_menus.py`)

## Thêm module coach = 1 yaml + 1 Hermes profile
1. Tạo Hermes profile trên VPS (xem `docs/modules/hermes-vps-multi-profile-setup.md`).
2. Tạo `~/.ted/modules/<id>/module.yaml`:
   ```yaml
   id: ly
   name: "Học Lý"
   icon: "🔬"
   engine: coach
   connection: ly
   enabled: true
   order: 50
   learner_id: con
   ```
3. Thêm connection `ly` trong Settings, khởi động lại Ted. Mục tiêu, môn, lịch học do Hermes trả về khi sync.
