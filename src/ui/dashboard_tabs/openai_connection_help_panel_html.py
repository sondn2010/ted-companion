"""Nội dung HTML cẩm nang tham số cho hộp thoại kết nối OpenAI-compatible (rich-text không đọc QSS nên build từ design tokens)."""

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
    📘 Cẩm Nang Tham Số Kỹ Thuật (OpenAI Compatible)
  </h3>
  <p style="color: {TEXT_MUTED}; font-size: 11px; margin-bottom: 10px;">
    Kết nối Não AI cho phép trợ lý Ted liên lạc với bất kỳ dịch vụ hoặc máy chủ AI nào hỗ trợ chuẩn <b>OpenAI Compatible API</b> (OpenAI, Ollama, vLLM, LM Studio, Groq, OpenRouter, v.v.).
  </p>

  <div style="background-color: {SURFACE_RAISED}; border-radius: 6px; padding: 8px 10px; margin-bottom: 8px; border-left: 3px solid {PRIMARY};">
    <b style="color: {PRIMARY}; font-size: 11px;">🌐 Địa chỉ máy chủ (Base URL)</b><br>
    <span style="color: {TEXT}; font-size: 11px;">
      • <b>VPS Cloud / Đám mây:</b> Địa chỉ máy chủ VPS, ví dụ <code>http://100.x.y.z:8000/v1</code> hoặc <code>https://api.openai.com/v1</code>.<br>
      • <b>Local Offline:</b> Máy chủ chạy ngay trên máy tính của bạn (vd Ollama: <code>http://127.0.0.1:11434/v1</code> hoặc vLLM/LM Studio: <code>http://127.0.0.1:8000/v1</code>).<br>
      <i>⚠️ Lưu ý: Đường dẫn URL thông thường cần có <code>/v1</code> ở cuối.</i>
    </span>
  </div>

  <div style="background-color: {SURFACE_RAISED}; border-radius: 6px; padding: 8px 10px; margin-bottom: 8px; border-left: 3px solid {SECONDARY_SOFT};">
    <b style="color: {SECONDARY_SOFT}; font-size: 11px;">🔑 Khóa bảo mật (API Key)</b><br>
    <span style="color: {TEXT}; font-size: 11px;">
      Chuỗi API Key để xác thực với nhà cung cấp (OpenAI, OpenRouter, Groq, hoặc khóa tùy chỉnh trên VPS cá nhân). Nếu dùng mô hình Local không yêu cầu xác thực, bạn có thể để trống.
    </span>
  </div>

  <div style="background-color: {SURFACE_RAISED}; border-radius: 6px; padding: 8px 10px; margin-bottom: 12px; border-left: 3px solid {TERTIARY};">
    <b style="color: {TERTIARY}; font-size: 11px;">🤖 Tên mô hình (Model ID)</b><br>
    <span style="color: {TEXT}; font-size: 11px;">
      Tên model AI sẽ được gọi, ví dụ: <code>gpt-4o-mini</code>, <code>gpt-4o</code>, <code>qwen2.5:latest</code>, <code>llama3.2</code>, v.v.
    </span>
  </div>

  <hr style="border: none; border-top: 1px solid {OUTLINE_STRONG}; margin: 10px 0;">

  <div style="background-color: {SURFACE_REASONING}; border: 1px solid {SECONDARY}; border-radius: 6px; padding: 10px;">
    <b style="color: {WARNING}; font-size: 11px;">👨‍💻 Hỗ Trợ & Đóng Góp:</b><br>
    <div style="color: {TEXT}; font-size: 11px; margin-top: 4px; line-height: 1.5;">
      • <b>Tác giả:</b> Son Do<br>
      • <b>Email:</b> <a href="mailto:sondn2010@gmail.com" style="color: {PRIMARY}; text-decoration: none; font-weight: bold;">sondn2010@gmail.com</a><br>
      <span style="color: {TEXT_MUTED}; font-size: 10px;">
        <i>Hỗ trợ tích hợp mọi endpoint OpenAI-compatible cho các giải pháp cá nhân và doanh nghiệp.</i>
      </span>
    </div>
  </div>
</div>
"""
