"""Unit tests cho ActivityClassifier, WindowInspector và ActivityReportBuilder."""

import json
import pytest
from src.core.activity_watcher.activity_classifier import (
    ActivityCategory,
    ActivityClassifier,
)
from src.core.activity_watcher.activity_report_builder import (
    build_activity_report_dict,
    format_ted_activity_report_message,
)
from src.core.activity_watcher.activity_table_models import DailyActivityRecord
from src.core.activity_watcher.window_inspector import ActiveWindowInfo, WindowInspector


def test_classifier_identifies_study_apps():
    classifier = ActivityClassifier()

    # Word
    res = classifier.classify("De_thi_Toan_HK1.docx - Microsoft Word", "winword.exe")
    assert res.category == ActivityCategory.STUDY
    assert "Word" in res.app_name

    # GeoGebra
    res = classifier.classify("GeoGebra Classic 6", "geogebra.exe")
    assert res.category == ActivityCategory.STUDY

    # Khan Academy in browser
    res = classifier.classify("Khan Academy | Luyện tập Đại số 8 - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.STUDY
    assert "Khan Academy" in res.app_name
    assert res.is_browser is True

    # Sách Mềm
    res = classifier.classify("Sách Mềm - Tiếng Anh 8 Global Success", "msedge.exe")
    assert res.category == ActivityCategory.STUDY


def test_classifier_identifies_distractions():
    classifier = ActivityClassifier()

    # TikTok
    res = classifier.classify("TikTok - Make Your Day - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "TikTok" in res.app_name

    # YouTube Shorts
    res = classifier.classify("Funny cat videos #shorts - YouTube", "chrome.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "YouTube Shorts" in res.app_name

    # Facebook
    res = classifier.classify("Facebook - Bảng tin - Cốc Cốc", "coccoc.exe")
    assert res.category == ActivityCategory.DISTRACTION

    # Roblox
    res = classifier.classify("Roblox Player", "robloxplayerbeta.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "Roblox" in res.app_name


def test_classifier_identifies_chatchit_and_social_media():
    classifier = ActivityClassifier()

    # Zalo Desktop App
    res = classifier.classify("Nguyễn Văn A - Zalo", "zalo.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "Zalo" in res.app_name

    # Zalo Web
    res = classifier.classify("Zalo Web - Đăng nhập - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "Zalo" in res.app_name

    # Messenger
    res = classifier.classify("Messenger - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "Messenger" in res.app_name

    # Telegram Desktop App
    res = classifier.classify("Telegram", "telegram.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "Telegram" in res.app_name

    # WhatsApp Web
    res = classifier.classify("(1) WhatsApp - Microsoft Edge", "msedge.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "WhatsApp" in res.app_name

    # Discord App
    res = classifier.classify("Discord", "discord.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "Discord" in res.app_name

    # YouTube Video
    res = classifier.classify("Sơn Tùng M-TP - Đừng Làm Trái Tim Anh Đau - YouTube - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "YouTube" in res.app_name

    # Instagram
    res = classifier.classify("Instagram - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "Instagram" in res.app_name

    # Threads
    res = classifier.classify("Threads - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "Threads" in res.app_name

    # X / Twitter
    res = classifier.classify("X - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "X / Twitter" in res.app_name

    # Reddit
    res = classifier.classify("Reddit - Dive into anything - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.DISTRACTION
    assert "Reddit" in res.app_name


def test_classifier_normal_web_tabs_are_not_distractions():
    classifier = ActivityClassifier()

    # 1. Tìm kiếm Google có chứa từ khóa mạng xã hội/chat -> KHÔNG phải xao nhãng (NEUTRAL)
    res = classifier.classify("cách tải video youtube về máy - Tìm trên Google - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.NEUTRAL
    assert res.category != ActivityCategory.DISTRACTION

    res = classifier.classify("cách tạo tài khoản zalo web - Tìm trên Google - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.NEUTRAL
    assert res.category != ActivityCategory.DISTRACTION

    res = classifier.classify("best fishing reels 2026 - Google Search - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.NEUTRAL
    assert res.category != ActivityCategory.DISTRACTION

    # 2. Đọc tin tức báo chí có bài viết nhắc đến mạng xã hội -> KHÔNG phải xao nhãng (NEUTRAL)
    res = classifier.classify("Mỹ chuẩn bị dự luật cấm TikTok - Báo VnExpress - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.NEUTRAL
    assert res.category != ActivityCategory.DISTRACTION

    res = classifier.classify("Meta cập nhật thuật toán Facebook - Báo điện tử Dân Trí - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.NEUTRAL
    assert res.category != ActivityCategory.DISTRACTION

    # 3. Tra cứu bách khoa / tài liệu kỹ thuật
    res = classifier.classify("Steam locomotive history - Britannica - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.NEUTRAL
    assert res.category != ActivityCategory.DISTRACTION

    # 4. Trang web thông thường bất kỳ -> NEUTRAL mặc định, không bao giờ là DISTRACTION
    res = classifier.classify("Lịch sử hình thành chữ Quốc ngữ - Cốc Cốc", "coccoc.exe")
    assert res.category == ActivityCategory.NEUTRAL
    assert res.is_browser is True

    # 5. Công cụ AI và lập trình học tập trên Web -> STUDY (Học tập & Làm việc)
    res = classifier.classify("ChatGPT - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.STUDY
    assert "ChatGPT" in res.app_name

    res = classifier.classify("Claude - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.STUDY
    assert "Claude" in res.app_name

    res = classifier.classify("GitHub - my-repo - Brave", "brave.exe")
    assert res.category == ActivityCategory.STUDY
    assert "GitHub" in res.app_name

    res = classifier.classify("python - How to parse json - Stack Overflow - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.STUDY
    assert "Stack Overflow" in res.app_name

    res = classifier.classify("Báo cáo môn Ngữ Văn - Google Docs - Google Chrome", "chrome.exe")
    assert res.category == ActivityCategory.STUDY
    assert "Google Docs" in res.app_name


def test_classifier_identifies_unsafe_content():
    classifier = ActivityClassifier()

    # Adult
    res = classifier.classify("xvideos - watch free videos", "chrome.exe")
    assert res.category == ActivityCategory.UNSAFE

    # Gambling
    res = classifier.classify("Kubet Casino Trực Tuyến Uy Tín", "msedge.exe")
    assert res.category == ActivityCategory.UNSAFE


def test_classifier_neutral_and_empty():
    classifier = ActivityClassifier()

    # File Explorer
    res = classifier.classify("D:\\BaiTap", "explorer.exe")
    assert res.category == ActivityCategory.NEUTRAL

    # Empty
    res = classifier.classify("", "")
    assert res.category == ActivityCategory.NEUTRAL


def test_window_inspector_with_mock_backend():
    mock_data = ActiveWindowInfo(
        title="TikTok - Make Your Day",
        process_name="chrome.exe",
        hwnd=12345,
        pid=999
    )
    inspector = WindowInspector(backend_fn=lambda: mock_data)
    win = inspector.get_active_window()
    assert win is not None
    assert win.title == "TikTok - Make Your Day"
    assert win.process_name == "chrome.exe"
    assert win.pid == 999


def test_report_builder_creates_valid_payload():
    rec = DailyActivityRecord(
        date="2026-10-22",
        learner="uyen",
        study_seconds=5400,        # 90 phút
        distraction_seconds=900,   # 15 phút
        neutral_seconds=600,       # 10 phút
        unsafe_attempts=0,
        self_corrected_count=3,
        breach_count=0,
        top_apps_json=json.dumps({"Microsoft Word": 3000, "TikTok": 900, "GeoGebra": 2400}),
    )

    data = build_activity_report_dict(rec)
    assert data["kind"] == "daily_activity"
    assert data["date"] == "2026-10-22"
    assert data["learner"] == "uyen"
    assert data["study_minutes"] == 90.0
    assert data["distraction_minutes"] == 15.0
    assert data["focus_percentage"] > 80.0
    assert data["self_corrected_count"] == 3
    assert data["status"] == "good"

    msg = format_ted_activity_report_message(data)
    assert msg.startswith("[TED_ACTIVITY_REPORT]\n<json>")
    assert "</json>" in msg
