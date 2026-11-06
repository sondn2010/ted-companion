# Nhân vật mở khoá dần (Unlockable skin packs)

Thư mục này chứa các pack nhân vật được **đóng gói sẵn** trong app. Mỗi nhân vật có **điều kiện mở khoá riêng**
(số huy hiệu, chỉ số trọn đời, huy hiệu cụ thể...). Đã mở là **vĩnh viễn** (bảng `SkinUnlock`, reset level tuần
không khoá lại). 6 con vật mặc định luôn miễn phí. Người dùng chọn nhân vật ở trang Dashboard **🎭 Nhân vật**
(menu chuột phải / khay hệ thống / Cài đặt đều dẫn tới đó).

```
assets/unlockable_skin_packs/
  skin_unlock_registry.json     # điều kiện từng nhân vật (sửa tay được)
  <pack>/characters.json        # + ảnh PNG đã thu nhỏ (script tạo, đừng sửa tay)
```
Key nhân vật = `<pack>/<character_id>`. Ảnh luôn thu nhỏ về **256px** (cạnh dài, giữ alpha) và chỉ giữ ảnh app dùng
(5 trạng thái idle/focus/cheer/rest/nudge + avatar) → 6 pack × 6 nhân vật ≈ 12 MB. Ảnh gốc (1024×1536) không đóng gói.

## Thêm / gỡ pack (script)
```bash
cd ted-companion
uv run python scripts/install_unlockable_skin_packs.py --pack 01_chibi_adult_mature --pack vietnam-chibi-pack
uv run python scripts/install_unlockable_skin_packs.py --list
uv run python scripts/install_unlockable_skin_packs.py --remove vietnam-chibi-pack
```
| Tham số | Ý nghĩa |
|---|---|
| `--pack <tên\|đường dẫn>` | Pack cần cài (lặp lại được). Tên = thư mục trong `--source` |
| `--source <thư mục>` | Nơi chứa pack gốc (mặc định `../docs/UI/characters`, chỉ đọc, không bao giờ bị sửa) |
| `--size 256` | Cạnh dài tối đa của ảnh (px) |
| `--remove <pack>` | Gỡ pack + các dòng registry của nó (lặp lại được) |
| `--list` | Liệt kê pack đã cài + điều kiện + dung lượng |
| `--dry-run` | Chỉ kiểm tra và in kế hoạch, không ghi gì |
| `--yes` | Không hỏi khi pack thiếu ảnh trạng thái |

Script idempotent, kiểm tra 5 ảnh trạng thái mỗi nhân vật (in nhân vật thiếu ảnh, hỏi trước khi tiếp tục; nhân vật
không có ảnh nào thì dừng). Nhân vật MỚI được nối đuôi registry với **bậc thang điều kiện tự động** (xen kẽ số huy
hiệu và mục tiêu chỉ số, khó dần); điều kiện đã có trong registry **không bao giờ bị ghi đè**. Thả tay thêm 1 thư mục
pack mà chưa có trong registry vẫn hiện, với điều kiện tự gán (không bao giờ miễn phí do quên khai báo).
Asset đã commit nên không cần chạy script khi build; chỉ chạy khi đổi danh sách pack.

## Định dạng `skin_unlock_registry.json`
```json
{"version": 1, "skins": [
  {"key": "vietnam-chibi-pack/linh", "pack": "vietnam-chibi-pack", "name_vi": "Linh", "name_en": "Linh",
   "unlock": {"type": "badges", "count": 5}}
]}
```
Thứ tự trong file = thứ tự hiển thị trong từng nhóm. Entry sai định dạng bị bỏ qua (nhân vật nhận điều kiện tự gán).

## Loại điều kiện (`unlock`)
| `type` | Trường | Mở khi |
|---|---|---|
| `free` | — | Mở ngay |
| `badges` | `count` | Số huy hiệu khác nhau đã mở ≥ count |
| `badge` | `id` | Đã có huy hiệu `id` (xem `assets/badges/badge_catalog.json`) |
| `metric` | `metric`, `value` | Chỉ số trọn đời ≥ value |

Chỉ số (`metric`): `focus_sessions` (phiên Deep Work), `focus_minutes`, `tasks_done`, `quiz_answered` (bài tập đã
làm), `quiz_correct` (câu đúng), `writing_graded`, `agenda_done`, `untangle_sessions` (phiên Gỡ Rối), `peak_level`
(level cao nhất từng đạt), `best_streak_days`, `active_days`, `outings`, `xp_total`.

Điều kiện được đánh giá mỗi lần Hub làm mới (sau phiên tập trung, xong việc, mỗi vài phút); nhân vật mới mở sẽ hiện
bubble "🎭 Mở khóa nhân vật mới: ...". `FocusEngine.set_character` từ chối nhân vật chưa mở (cả lệnh MCP bên ngoài).
Biến môi trường `TED_UNLOCKABLE_SKIN_PACKS_DIR` đọc pack từ thư mục khác (test trỏ vào thư mục rỗng).
