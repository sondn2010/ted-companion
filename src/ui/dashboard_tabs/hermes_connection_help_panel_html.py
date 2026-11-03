"""Nội dung HTML cẩm nang tham số cho hộp thoại kết nối Hermes (rich-text không đọc QSS nên build từ design tokens)."""

from src.ui.theme.design_tokens import (
    OUTLINE_STRONG,
    PRIMARY,
    PRIMARY_SOFT,
    SECONDARY,
    SECONDARY_SOFT,
    SURFACE_RAISED,
    SURFACE_REASONING,
    TERTIARY,
    TEXT,
    TEXT_MUTED,
    WARNING,
)

HELP_PANEL_HTML = f"""
<div style="font-family: 'Segoe UI', sans-serif; color: {TEXT}; line-height: 1.45;">
  <h3 style="color: {PRIMARY_SOFT}; margin-top: 0; margin-bottom: 8px; font-size: 14px;">
    📘 Cẩm Nang Tham Số Kỹ Thuật
  </h3>
  <p style="color: {TEXT_MUTED}; font-size: 11px; margin-bottom: 10px;">
    Kết nối Não AI cho phép trợ lý Ted liên lạc với "Não bộ AI" để lưu trữ ký ức dài hạn, lập kế hoạch và phân tích nhiệm vụ.
  </p>

  <div style="background-color: {SURFACE_RAISED}; border-radius: 6px; padding: 8px 10px; margin-bottom: 8px; border-left: 3px solid {PRIMARY};">
    <b style="color: {PRIMARY}; font-size: 11px;">🌐 Địa chỉ máy chủ (Base URL)</b><br>
    <span style="color: {TEXT}; font-size: 11px;">
      • <b>VPS Cloud (Khuyên dùng):</b> Địa chỉ máy chủ đám mây, vd qua Tailscale <code>http://100.x.y.z:8080/v1</code>.<br>
      • <b>Local Offline:</b> Chạy ngay trên máy tính của bạn tại <code>http://127.0.0.1:8000/v1</code>.<br>
      <i>⚠️ Lưu ý: Luôn có <code>/v1</code> ở cuối đường dẫn.</i>
    </span>
  </div>

  <div style="background-color: {SURFACE_RAISED}; border-radius: 6px; padding: 8px 10px; margin-bottom: 8px; border-left: 3px solid {SECONDARY_SOFT};">
    <b style="color: {SECONDARY_SOFT}; font-size: 11px;">🔑 Khóa bảo mật (API Key)</b><br>
    <span style="color: {TEXT}; font-size: 11px;">
      Chuỗi mật mã bảo vệ máy chủ VPS của bạn khỏi truy cập trái phép. Lấy giá trị trong file <code>.env</code> trên VPS (dòng <code>API_SERVER_KEY=...</code>). Nếu chạy Local không đặt khóa thì có thể để trống.
    </span>
  </div>

  <div style="background-color: {SURFACE_RAISED}; border-radius: 6px; padding: 8px 10px; margin-bottom: 12px; border-left: 3px solid {TERTIARY};">
    <b style="color: {TERTIARY}; font-size: 11px;">🤖 Tên mô hình (Model ID)</b><br>
    <span style="color: {TEXT}; font-size: 11px;">
      Mô hình trí tuệ nhân tạo sẽ suy nghĩ và trả lời bạn. Khuyên dùng <code>google/gemini-2.5-flash</code> (rất nhanh, thông minh và kinh tế) hoặc <code>qwen-2.5-coder</code>.
    </span>
  </div>

  <hr style="border: none; border-top: 1px solid {OUTLINE_STRONG}; margin: 10px 0;">

  <div style="background-color: {SURFACE_REASONING}; border: 1px solid {SECONDARY}; border-radius: 6px; padding: 10px;">
    <b style="color: {WARNING}; font-size: 11px;">👨‍💻 Tác Giả & Hỗ Trợ Kỹ Thuật:</b><br>
    <div style="color: {TEXT}; font-size: 11px; margin-top: 4px; line-height: 1.5;">
      • <b>Tác giả:</b> Son Do<br>
      • <b>Email:</b> <a href="mailto:sondn2010@gmail.com" style="color: {PRIMARY}; text-decoration: none; font-weight: bold;">sondn2010@gmail.com</a><br>
      <span style="color: {TEXT_MUTED}; font-size: 10px;">
        <i>Liên hệ trực tiếp tác giả nếu bạn cần hỗ trợ cài đặt VPS 24/7, mạng riêng ảo Tailscale hoặc tùy biến trợ lý cho cả gia đình!</i>
      </span>
    </div>
  </div>
</div>
"""
