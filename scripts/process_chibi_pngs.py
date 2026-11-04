#!/usr/bin/env python3
"""
Script xử lý và tối ưu hóa bộ ảnh PNG Chibi cho Ted Companion:
- Tự động tách nền (background removal) thông minh từ màu nền pastel / biên ngoài của sticker
- Làm mịn viền (anti-aliased alpha edge) giữ trọn vẹn viền sticker trắng sang xịn
- Xuất file PNG trong suốt chuẩn 32-bit RGBA vào thư mục assets/animations_png_preview
- Sinh trang HTML Preview tương tác sống động để người dùng xem trực tiếp trên trình duyệt
"""

import os
import sys
from pathlib import Path
from collections import deque
from PIL import Image, ImageFilter

TARGET_DIR = Path(__file__).resolve().parent.parent / "assets" / "animations_png_preview"


def clean_cutout(input_path: str, output_path: str, thresh: float = 48.0):
    """
    Tách nền từ các cạnh biên ngoài vào đến viền sticker trắng của ảnh chibi.
    """
    img = Image.open(input_path).convert("RGBA")
    w, h = img.size
    pixels = img.load()

    # Lấy mẫu màu nền từ các điểm rìa ngoài cùng
    border_pts = []
    for x in range(0, w, 20):
        border_pts.extend([(x, 0), (x, h - 1)])
    for y in range(0, h, 20):
        border_pts.extend([(0, y), (w - 1, y)])

    bg_samples = [pixels[pt][:3] for pt in border_pts]
    avg_r = sum(c[0] for c in bg_samples) / len(bg_samples)
    avg_g = sum(c[1] for c in bg_samples) / len(bg_samples)
    avg_b = sum(c[2] for c in bg_samples) / len(bg_samples)

    visited = bytearray(w * h)
    queue = deque()

    # Bắt đầu BFS từ toàn bộ viền xung quanh
    for x in range(w):
        queue.append((x, 0))
        queue.append((x, h - 1))
        visited[0 * w + x] = 1
        visited[(h - 1) * w + x] = 1
    for y in range(h):
        queue.append((0, y))
        queue.append((w - 1, y))
        visited[y * w + 0] = 1
        visited[y * w + (w - 1)] = 1

    def color_dist(c1, c2):
        return ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2) ** 0.5

    # BFS tìm các pixel thuộc nền bên ngoài
    bg_mask = Image.new("L", (w, h), 255)
    mask_pixels = bg_mask.load()

    while queue:
        cx, cy = queue.popleft()
        r, g, b, _ = pixels[cx, cy]
        mask_pixels[cx, cy] = 0

        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                idx = ny * w + nx
                if not visited[idx]:
                    nr, ng, nb, _ = pixels[nx, ny]
                    # Nếu màu gần với màu nền trung bình -> tiếp tục loang
                    if color_dist((nr, ng, nb), (avg_r, avg_g, avg_b)) < thresh:
                        visited[idx] = 1
                        queue.append((nx, ny))

    # Làm mềm viền alpha để không bị răng cưa
    smooth_mask = bg_mask.filter(ImageFilter.GaussianBlur(radius=0.8))
    img.putalpha(smooth_mask)

    # Cắt gọn bounding box (crop sát nhân vật nhưng để chừa lề 16px)
    bbox = img.getbbox()
    if bbox:
        pad = 16
        crop_box = (
            max(0, bbox[0] - pad),
            max(0, bbox[1] - pad),
            min(w, bbox[2] + pad),
            min(h, bbox[3] + pad),
        )
        img = img.crop(crop_box)

    img.save(output_path, "PNG", optimize=True)
    print(f"  [+] Đã xuất PNG chất lượng cao: {Path(output_path).name}")


def generate_html_preview(output_html_path: str):
    html_content = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ted Companion - Chibi PNG Animations Showcase</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=Quicksand:wght@500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0F172A;
      --card-bg: rgba(30, 41, 59, 0.7);
      --card-border: rgba(255, 255, 255, 0.1);
      --accent: #F43F5E;
      --accent-glow: rgba(244, 63, 94, 0.4);
      --text: #F8FAFC;
      --text-muted: #94A3B8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', sans-serif;
      background: radial-gradient(circle at 50% 0%, #1E1B4B 0%, #0F172A 70%, #090D16 100%);
      color: var(--text);
      min-height: 100vh;
      padding: 40px 24px;
    }
    .header {
      text-align: center;
      max-width: 800px;
      margin: 0 auto 40px;
    }
    .badge {
      display: inline-block;
      padding: 6px 16px;
      background: linear-gradient(135deg, #EC4899, #8B5CF6);
      border-radius: 9999px;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      margin-bottom: 16px;
      box-shadow: 0 4px 15px rgba(236, 72, 153, 0.3);
    }
    h1 {
      font-size: 38px;
      font-weight: 800;
      letter-spacing: -0.5px;
      margin-bottom: 12px;
      background: linear-gradient(to right, #FFF, #CBD5E1);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    p.subtitle {
      font-size: 17px;
      color: var(--text-muted);
      line-height: 1.6;
    }
    .char-nav {
      display: flex;
      justify-content: center;
      gap: 16px;
      margin-bottom: 36px;
      flex-wrap: wrap;
    }
    .char-tab {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 12px 28px;
      border-radius: 16px;
      background: rgba(30, 41, 59, 0.8);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      cursor: pointer;
      font-size: 16px;
      font-weight: 700;
      transition: all 0.25s ease;
      backdrop-filter: blur(12px);
    }
    .char-tab:hover {
      color: #FFF;
      border-color: rgba(255, 255, 255, 0.3);
      transform: translateY(-2px);
    }
    .char-tab.active {
      color: #FFF;
      background: linear-gradient(135deg, #3B82F6, #8B5CF6);
      border-color: transparent;
      box-shadow: 0 8px 24px rgba(99, 102, 241, 0.4);
    }

    /* Live Interactive Widget Stage */
    .stage-section {
      max-width: 900px;
      margin: 0 auto 50px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 24px;
      padding: 32px;
      backdrop-filter: blur(16px);
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
    }
    .stage-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      flex-wrap: wrap;
      gap: 16px;
    }
    .stage-title {
      font-size: 20px;
      font-weight: 700;
    }
    .controls-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .mood-btn {
      padding: 8px 18px;
      border-radius: 12px;
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: var(--text-muted);
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .mood-btn:hover { color: #FFF; border-color: rgba(255, 255, 255, 0.4); }
    .mood-btn.active {
      background: #F43F5E;
      border-color: #F43F5E;
      color: #FFF;
      box-shadow: 0 4px 12px var(--accent-glow);
    }
    .canvas-box {
      height: 320px;
      border-radius: 18px;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      overflow: hidden;
      transition: background 0.3s ease;
      background: #111827;
      background-image: 
        linear-gradient(45deg, #1F2937 25%, transparent 25%), 
        linear-gradient(-45deg, #1F2937 25%, transparent 25%), 
        linear-gradient(45deg, transparent 75%, #1F2937 75%), 
        linear-gradient(-45deg, transparent 75%, #1F2937 75%);
      background-size: 24px 24px;
      background-position: 0 0, 0 12px, 12px -12px, -12px 0px;
    }
    .companion-avatar {
      width: 220px;
      height: 220px;
      object-fit: contain;
      cursor: grab;
      filter: drop-shadow(0 16px 24px rgba(0,0,0,0.45));
      animation: floatBreath 3.2s ease-in-out infinite;
      transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
    }
    .companion-avatar:hover {
      transform: scale(1.12) rotate(-3deg);
      filter: drop-shadow(0 20px 30px rgba(0,0,0,0.6));
    }
    .companion-avatar:active {
      transform: scale(0.95);
      cursor: grabbing;
    }
    @keyframes floatBreath {
      0%, 100% { transform: translateY(0px) scale(1, 1); }
      50% { transform: translateY(-12px) scale(1.02, 0.98); }
    }

    /* Grid of All Moods */
    .grid-section {
      max-width: 1200px;
      margin: 0 auto;
    }
    .grid-title {
      font-size: 22px;
      font-weight: 700;
      margin-bottom: 20px;
      text-align: center;
    }
    .mood-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 24px;
    }
    .mood-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 20px;
      padding: 24px 18px 20px;
      text-align: center;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      backdrop-filter: blur(12px);
      position: relative;
    }
    .mood-card:hover {
      transform: translateY(-8px);
      border-color: rgba(255, 255, 255, 0.3);
      box-shadow: 0 16px 32px rgba(0,0,0,0.5);
    }
    .card-img-wrap {
      width: 100%;
      height: 180px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 16px;
      background: radial-gradient(circle, rgba(255,255,255,0.06) 0%, transparent 70%);
      border-radius: 14px;
    }
    .mood-card img {
      max-width: 150px;
      max-height: 150px;
      object-fit: contain;
      filter: drop-shadow(0 10px 18px rgba(0,0,0,0.35));
      transition: transform 0.25s ease;
    }
    .mood-card:hover img {
      transform: scale(1.1);
    }
    .mood-name {
      font-size: 17px;
      font-weight: 700;
      margin-bottom: 6px;
    }
    .mood-desc {
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.4;
    }
    .file-badge {
      display: inline-block;
      margin-top: 10px;
      padding: 4px 10px;
      border-radius: 6px;
      background: rgba(255,255,255,0.08);
      font-size: 11px;
      font-family: monospace;
      color: #CBD5E1;
    }
  </style>
</head>
<body>

  <div class="header">
    <div class="badge">✨ Ted Companion Visual Refresh</div>
    <h1>Bộ Sưu Tập Chibi PNG Animations</h1>
    <p class="subtitle">Thử nghiệm diện mạo mới cho Cún Shiba, Thỏ Bông và Cánh Cụt Mini. Độ phân giải cao, viền sticker cắt khuôn tinh tế, định dạng PNG trong suốt tối ưu cho Desktop Pet.</p>
  </div>

  <!-- Character Selector -->
  <div class="char-nav">
    <button class="char-tab active" onclick="switchChar('cat')">🐱 Mèo Ted</button>
    <button class="char-tab" onclick="switchChar('shiba')">🐕 Cún Shiba</button>
    <button class="char-tab" onclick="switchChar('bunny')">🐰 Thỏ Bông</button>
    <button class="char-tab" onclick="switchChar('penguin')">🐧 Cánh Cụt</button>
    <button class="char-tab" onclick="switchChar('owl')">🦉 Cú Đêm</button>
    <button class="char-tab" onclick="switchChar('panda')">🐼 Gấu Trúc</button>
  </div>

  <!-- Live Simulation Stage -->
  <div class="stage-section">
    <div class="stage-header">
      <div class="stage-title">🎮 Xem Thử Mô Phỏng Tương Tác</div>
      <div class="controls-row">
        <button class="mood-btn active" onclick="switchMood('idle')">Idle (Bình thường)</button>
        <button class="mood-btn" onclick="switchMood('focus')">Focus (Tập trung)</button>
        <button class="mood-btn" onclick="switchMood('cheer')">Cheer (Ăn mừng)</button>
        <button class="mood-btn" onclick="switchMood('rest')">Rest (Nghỉ ngơi)</button>
        <button class="mood-btn" onclick="switchMood('nudge')">Nudge (Nhắc việc)</button>
      </div>
    </div>
    <div class="canvas-box" id="stageCanvas">
      <img id="liveAvatar" class="companion-avatar" src="cat_idle.png" alt="Companion Avatar" />
    </div>
    <div style="text-align: center; margin-top: 14px; font-size: 13px; color: var(--text-muted);">
      💡 Di chuột vào để xem hiệu ứng Hover, Click chuột để trải nghiệm phản hồi xúc giác như trên Widget máy tính.
    </div>
  </div>

  <!-- All Moods Grid -->
  <div class="grid-section">
    <div class="grid-title" id="gridHeaderTitle">Toàn Bộ 5 Biểu Cảm Của Mèo Ted</div>
    <div class="mood-grid" id="moodGridContainer">
      <!-- Injected by JavaScript -->
    </div>
  </div>

  <script>
    const CHAR_DATA = {
      cat: {
        name: "Mèo Ted (Cat)",
        moods: [
          { key: "idle", label: "Idle", desc: "Mèo vàng cam đáng yêu, chuông vàng leng keng, ngồi ngoan ngoãn mỉm cười.", file: "cat_idle.png" },
          { key: "focus", label: "Focus", desc: "Đeo tai nghe gaming có mic và kính cận, chăm chú gõ phím làm việc.", file: "cat_focus.png" },
          { key: "cheer", label: "Cheer", desc: "Giơ 2 chân ăn mừng rực rỡ, sao lấp lánh và hoa giấy rộn ràng.", file: "cat_cheer.png" },
          { key: "rest", label: "Rest", desc: "Cuộn tròn ngủ say như ổ bánh mì bơ trên gối, Zzz nhẹ nhàng êm ái.", file: "cat_rest.png" },
          { key: "nudge", label: "Nudge", desc: "Nghiêng đầu tò mò, giơ đệm chân hồng vẫy gọi nhắc việc cùng dấu hỏi chấm.", file: "cat_nudge.png" }
        ]
      },
      shiba: {
        name: "Cún Shiba",
        moods: [
          { key: "idle", label: "Idle", desc: "Mỉm cười dễ thương, chuông vàng leng keng, vẫy đuôi nhẹ nhàng.", file: "shiba_idle.png" },
          { key: "focus", label: "Focus", desc: "Đeo tai nghe gaming và kính học bài, tập trung cao độ làm việc.", file: "shiba_focus.png" },
          { key: "cheer", label: "Cheer", desc: "Giơ 2 chân ăn mừng phấn khích, sao lấp lánh và hoa giấy rực rỡ.", file: "shiba_cheer.png" },
          { key: "rest", label: "Rest", desc: "Cuộn tròn ngủ say như bánh mì bơ, Zzz lơ lửng, thư thái an yên.", file: "shiba_rest.png" },
          { key: "nudge", label: "Nudge", desc: "Nghiêng đầu tò mò với dấu hỏi chấm, nhắc nhở nhẹ nhàng.", file: "shiba_nudge.png" }
        ]
      },
      bunny: {
        name: "Thỏ Bông",
        moods: [
          { key: "idle", label: "Idle", desc: "Thỏ trắng tai cụp ôm củ cà rốt nhỏ, hoa anh đào cài tai ngọt ngào.", file: "bunny_idle.png" },
          { key: "focus", label: "Focus", desc: "Đeo tai nghe cyber hồng và kính tròn, chăm chú học tập và làm việc.", file: "bunny_focus.png" },
          { key: "cheer", label: "Cheer", desc: "Nhảy nhót vui mừng giơ tay chữ V, hoa anh đào và pháo hoa giấy tung bay.", file: "bunny_cheer.png" },
          { key: "rest", label: "Rest", desc: "Ôm gối ngủ say sưa, bóng khí Zzz phát sáng ấm áp, ngọt ngào.", file: "bunny_rest.png" },
          { key: "nudge", label: "Nudge", desc: "Nghiêng đầu nháy mắt nhắc nhở công việc, dấu chấm hỏi dễ thương.", file: "bunny_nudge.png" }
        ]
      },
      penguin: {
        name: "Cánh Cụt Mini",
        moods: [
          { key: "idle", label: "Idle", desc: "Quấn khăn len sọc ấm áp, dáng đứng tròn xoe múp míp lắc lư.", file: "penguin_idle.png" },
          { key: "focus", label: "Focus", desc: "Đeo tai nghe đèn LED dạ quang và kính cận, chuyên tâm hoàn thành task.", file: "penguin_focus.png" },
          { key: "cheer", label: "Cheer", desc: "Vỗ 2 cánh vẫy chào mừng chiến thắng, bông tuyết và ánh sao vàng rực rỡ.", file: "penguin_cheer.png" },
          { key: "rest", label: "Rest", desc: "Đội mũ len ngủ say sưa trong tổ ấm, giấc ngủ bình yên ngọt ngào.", file: "penguin_rest.png" },
          { key: "nudge", label: "Nudge", desc: "Gõ gõ cánh nhắc nhở giờ làm việc / giải lao với biểu cảm tinh nghịch.", file: "penguin_nudge.png" }
        ]
      },
      owl: {
        name: "Cú Đêm (Owl)",
        moods: [
          { key: "idle", label: "Idle", desc: "Bộ lông nâu vàng ấm áp, mắt hổ phách to tròn thông thái và đáng yêu.", file: "owl_idle.png" },
          { key: "focus", label: "Focus", desc: "Đeo tai nghe gaming neon xanh và kính đọc sách, chăm chỉ đọc sách nghiên cứu.", file: "owl_focus.png" },
          { key: "cheer", label: "Cheer", desc: "Vỗ cánh ăn mừng chiến thắng, ánh sao vàng và hoa giấy lung linh.", file: "owl_cheer.png" },
          { key: "rest", label: "Rest", desc: "Đội mũ ngủ say sưa trên gối trăng khuyết, giấc mơ ngọt ngào bình an.", file: "owl_rest.png" },
          { key: "nudge", label: "Nudge", desc: "Nghiêng đầu giơ cánh gõ nhắc việc, dấu chấm hỏi tò mò ngộ nghĩnh.", file: "owl_nudge.png" }
        ]
      },
      panda: {
        name: "Gấu Trúc (Panda)",
        moods: [
          { key: "idle", label: "Idle", desc: "Mochi tròn xoe ôm nhánh trúc xanh tươi non, quầng mắt đen lấp lánh nụ cười.", file: "panda_idle.png" },
          { key: "focus", label: "Focus", desc: "Đeo tai nghe gaming LED xanh lá cyber và kính tròn, ngồi thẳng thắn tập trung.", file: "panda_focus.png" },
          { key: "cheer", label: "Cheer", desc: "Giơ 2 tay múp míp ăn mừng phấn khích, lá trúc và pháo hoa rộn rã.", file: "panda_cheer.png" },
          { key: "rest", label: "Rest", desc: "Cuộn tròn như quả cầu tuyết ôm gối ngủ ngon lành, Zzz êm ái.", file: "panda_rest.png" },
          { key: "nudge", label: "Nudge", desc: "Nghiêng đầu giơ bàn chân đen bụ bẫm vẫy gọi nhắc nhở giờ học bài.", file: "panda_nudge.png" }
        ]
      }
    };

    let currentChar = 'cat';
    let currentMood = 'idle';

    function switchChar(charKey) {
      currentChar = charKey;
      document.querySelectorAll('.char-tab').forEach(b => b.classList.remove('active'));
      const activeBtn = Array.from(document.querySelectorAll('.char-tab')).find(b => b.getAttribute('onclick').includes(charKey));
      if (activeBtn) activeBtn.classList.add('active');

      updateLiveView();
      renderGrid();
    }

    function switchMood(moodKey) {
      currentMood = moodKey;
      document.querySelectorAll('.mood-btn').forEach(b => b.classList.remove('active'));
      const activeBtn = Array.from(document.querySelectorAll('.mood-btn')).find(b => b.getAttribute('onclick').includes(moodKey));
      if (activeBtn) activeBtn.classList.add('active');

      updateLiveView();
    }

    function updateLiveView() {
      const liveImg = document.getElementById('liveAvatar');
      liveImg.src = `${currentChar}_${currentMood}.png`;
    }

    function renderGrid() {
      const charInfo = CHAR_DATA[currentChar];
      document.getElementById('gridHeaderTitle').textContent = `Toàn Bộ 5 Biểu Cảm Của ${charInfo.name}`;
      const container = document.getElementById('moodGridContainer');
      container.innerHTML = '';

      charInfo.moods.forEach(m => {
        const card = document.createElement('div');
        card.className = 'mood-card';
        card.innerHTML = `
          <div class="card-img-wrap">
            <img src="${m.file}" alt="${m.label}">
          </div>
          <div class="mood-name">${m.label}</div>
          <div class="mood-desc">${m.desc}</div>
          <span class="file-badge">${m.file}</span>
        `;
        card.onclick = () => switchMood(m.key);
        container.appendChild(card);
      });
    }

    // Init
    renderGrid();
  </script>
</body>
</html>
"""
    Path(output_html_path).write_text(html_content, encoding="utf-8")
    print(f"[+] Đã tạo trang HTML Showcase: {output_html_path}")


if __name__ == "__main__":
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    generate_html_preview(TARGET_DIR / "preview.html")
