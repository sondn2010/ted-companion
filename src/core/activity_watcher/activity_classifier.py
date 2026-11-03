"""Bộ phân loại ứng dụng & cửa sổ đang hoạt động (Activity Classifier).

Phân loại cửa sổ active theo 4 nhóm chính:
- STUDY: Ứng dụng/trang web học tập & làm việc (Word, Excel, PDF, LMS, GeoGebra, Zoom/Teams,
  Google Docs/Sheets/Drive, ChatGPT, Claude, Gemini, GitHub, Stack Overflow, từ điển, bài giảng...)
- DISTRACTION: Ứng dụng & nền tảng nhắn tin chatchit (Zalo, Messenger, Telegram, WhatsApp, Discord,
  Viber, Skype...) và mạng xã hội, video giải trí (TikTok, YouTube Shorts, YouTube, Facebook, Reels,
  Instagram, Threads, X/Twitter, Reddit, Game online, Web xem phim, truyện tranh...)
- UNSAFE: Trang web độc hại, cờ bạc, người lớn 18+
- NEUTRAL: Cửa sổ hệ thống, desktop, taskbar, cài đặt... và các tab duyệt web thông thường
  (tìm kiếm Google/Bing, tra cứu tài liệu, đọc báo tin tức chính thống, tham khảo thông tin...)

Nguyên tắc quan trọng:
"Không phải tab nào trên web cũng là xao nhãng" — Trình duyệt web khi mở tài liệu, tra cứu, đọc báo,
học tập, công cụ AI/lập trình... nếu không thuộc các nền tảng chat hoặc mạng xã hội/giải trí
nêu trên thì mặc định là NEUTRAL (hoặc STUDY nếu là trang học tập), tuyệt đối không bị coi là xao nhãng.
"""

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Dict, List, Optional, Tuple


class ActivityCategory(str, Enum):
    STUDY = "study"
    DISTRACTION = "distraction"
    UNSAFE = "unsafe"
    NEUTRAL = "neutral"


@dataclass
class ClassificationResult:
    category: ActivityCategory
    app_name: str
    matched_rule: str = ""
    is_browser: bool = False
    details: str = ""


# Danh sách mẫu mặc định tối ưu cho học tập & làm việc
DEFAULT_STUDY_RULES: List[Tuple[str, str]] = [
    # 1. Ứng dụng văn phòng & soạn thảo tài liệu
    (r"\bwinword\b|microsoft word|word\b", "Microsoft Word"),
    (r"\bpowerpnt\b|powerpoint", "Microsoft PowerPoint"),
    (r"\bexcel\b|microsoft excel", "Microsoft Excel"),
    (r"\bonenote\b", "OneNote"),
    (r"\bacrobat\b|acrodist|\bfoxit\b|\bsumatrapdf\b|pdf reader", "PDF Reader"),
    (r"google docs|google tài liệu|docs\.google\.com", "Google Docs"),
    (r"google sheets|google trang tính|sheets\.google\.com", "Google Sheets"),
    (r"google slides|google trang trình bày", "Google Slides"),
    (r"drive\.google\.com", "Google Drive"),
    (r"notion\.so|\bnotion\.exe\b", "Notion"),
    (r"canva\.com", "Canva"),

    # 2. Lập trình & Kỹ thuật & Trợ lý AI
    (r"code\.exe|visual studio code|vscode", "VS Code"),
    (r"pycharm|idle\b", "Python IDE"),
    (r"github\.com|gitlab\.com|\bgithub\b|\bgitlab\b", "GitHub / GitLab"),
    (r"stackoverflow\.com|stackexchange\.com|\bstack\s*overflow\b", "Stack Overflow"),
    (r"chatgpt\.com|chat\.openai\.com|\bchatgpt\b", "ChatGPT"),
    (r"claude\.ai|\bclaude\b", "Claude AI"),
    (r"gemini\.google\.com|\bgemini\b", "Google Gemini"),

    # 3. Lớp học trực tuyến & Họp
    (r"zoom\.exe|zoom workplace|zoom meeting", "Zoom"),
    (r"teams\.exe|microsoft teams", "Microsoft Teams"),
    (r"classin", "ClassIn"),
    (r"google meet|meet\.google\.com", "Google Meet"),
    (r"classroom\.google\.com", "Google Classroom"),

    # 4. Nền tảng học tập THCS/THPT & Khóa học trực tuyến
    (r"geogebra", "GeoGebra"),
    (r"desmos", "Desmos"),
    (r"scratch", "Scratch"),
    (r"duolingo", "Duolingo"),
    (r"anki", "Anki"),
    (r"khan\s*academy", "Khan Academy"),
    (r"wikipedia\.org|wikipedia", "Wikipedia"),
    (r"quizlet", "Quizlet"),
    (r"coursera|edx\.org", "Khóa học trực tuyến"),
    (r"hocmai|hocmai\.vn", "HOCMAI"),
    (r"vioedu|vio\.edu\.vn", "VioEdu"),
    (r"vietjack|vietjack\.com", "VietJack"),
    (r"loigiaihay|loigiaihay\.com", "Lời Giải Hay"),
    (r"olm\.vn|olm - trực tuyến", "OLM"),
    (r"tuyensinh247", "Tuyensinh247"),
    (r"onluyen\.vn", "Ôn Luyện"),
    (r"sachmem\.vn|sách mềm", "Sách Mềm"),
    (r"azota|azota\.vn", "Azota"),
    (r"vnedu|vnedu\.vn", "vnEdu"),
    (r"shub classroom|shub\.edu\.vn", "SHub Classroom"),
    (r"cambridge dictionary|oxford learners|từ điển|laban dictionary|tracnghiem\.net", "Từ điển & Luyện thi"),
]

# Các công cụ tìm kiếm và trang báo chí phổ biến:
# Đảm bảo khi người dùng tìm kiếm thông tin ("cách tải video youtube", "tạo tài khoản zalo")
# hoặc đọc báo có bài viết về mạng xã hội thì KHÔNG bị nhận nhầm thành xao nhãng.
DEFAULT_SEARCH_AND_NEWS_RULES: List[Tuple[str, str]] = [
    # Công cụ tìm kiếm Web
    (r"tìm trên google|google search|\bgoogle\.com/search\b", "Tìm kiếm Google"),
    (r"tìm kiếm trên bing|bing search|\bbing\.com/search\b", "Tìm kiếm Bing"),
    (r"duckduckgo", "Tìm kiếm DuckDuckGo"),
    (r"cốc cốc tìm kiếm|coc coc search", "Tìm kiếm Cốc Cốc"),
    # Báo chí & Tin tức chính thống
    (r"vnexpress\.net|\bvnexpress\b", "Báo VnExpress"),
    (r"dantri\.com\.vn|\bdân trí\b|dantri", "Báo Dân Trí"),
    (r"tuoitre\.vn|\btuổi trẻ\b|tuoitre", "Báo Tuổi Trẻ"),
    (r"thanhnien\.vn|\bthanh niên\b|thanhnien", "Báo Thanh Niên"),
    (r"vietnamnet\.vn|\bvietnamnet\b", "Báo VietNamNet"),
    (r"baomoi\.com|\bbaomoi\b", "Báo Mới"),
    (r"vtv\.vn|\bvtv\b", "Báo VTV"),
    (r"britannica", "Bách khoa Britannica"),
]

# Nhóm xao nhãng: Xác định rõ là chatchit trên Zalo, Messenger...
# hoặc mạng xã hội, video giải trí TikTok, YouTube, Facebook, Reels, Games...
DEFAULT_DISTRACTION_RULES: List[Tuple[str, str]] = [
    # 1. Ứng dụng & Nền tảng nhắn tin, chatchit (OTT & Web Chat)
    (r"\bzalo\.exe\b|chat\.zalo\.me|zalo\.me|\bzalo\b", "Zalo"),
    (r"messenger\.com|\bmessenger\.exe\b|\bmessenger\b", "Messenger"),
    (r"\btelegram\.exe\b|web\.telegram\.org|\bt\.me\b|\btelegram\b", "Telegram"),
    (r"\bwhatsapp\.exe\b|web\.whatsapp\.com|\bwhatsapp\b", "WhatsApp"),
    (r"\bviber\.exe\b|\bviber\b", "Viber"),
    (r"\bdiscord\.exe\b|discord\.com|\bdiscord\b", "Discord"),
    (r"\bskype\.exe\b|web\.skype\.com|\bskype\b", "Skype"),
    (r"\bwechat\.exe\b|weixin|\bwechat\b", "WeChat"),
    (r"\bline\.exe\b|line\.me", "LINE"),
    (r"\bkakaotalk\.exe\b|\bkakaotalk\b", "KakaoTalk"),

    # 2. Video ngắn & Mạng xã hội giải trí
    (r"tiktok\.com|\btiktok\.exe\b|\btiktok\b", "TikTok"),
    (r"youtube\.com/shorts|#shorts|\bshorts\b.*youtube", "YouTube Shorts"),
    (r"facebook\.com/reel|facebook reels|instagram\.com/reels", "Reels"),
    (r"facebook\.com|\bfb\.com\b|\bfacebook\b", "Facebook"),
    (r"instagram\.com|\binstagram\b", "Instagram"),
    (r"threads\.net|\bthreads\b", "Threads"),
    (r"twitter\.com|\bx\.com\b|\btwitter\b|\bx\b\s*[-–|/]|[-–|/]\s*\bx\b", "X / Twitter"),
    (r"reddit\.com|\breddit\b", "Reddit"),
    (r"snapchat\.com|\bsnapchat\b", "Snapchat"),
    (r"douyin\.com|\bdouyin\b", "Douyin"),
    (r"weibo\.com|\bweibo\b", "Weibo"),
    (r"pinterest\.com|\bpinterest\b", "Pinterest"),

    # 3. Streaming & Phim giải trí
    (r"youtube\.com|youtu\.be|\byoutube\b", "YouTube"),
    (r"netflix\.com|\bnetflix\b", "Netflix"),
    (r"bilibili\.tv|bilibili\.com", "Bilibili"),
    (r"iqiyi\.com|\biqiyi\b", "iQiyi"),
    (r"wetv\.vip|\bwetv\b", "WeTV"),
    (r"fptplay\.vn|\bfpt play\b", "FPT Play"),
    (r"vieon\.vn|\bvieon\b", "VieON"),
    (r"phimmoi|dongphim|motphim|ghienphim", "Web Xem Phim"),
    (r"twitch\.tv|\btwitch\.exe\b|\btwitch\s*tv\b", "Twitch"),
    (r"nimo\.tv|\bnimo tv\b", "Nimo TV"),

    # 4. Truyện tranh giải trí
    (r"nettruyen|truyenvn|manhwa|webtoon|mangadex|blogtruyen", "Web Đọc Truyện"),

    # 5. Game Online & Client game
    (r"\broblox\.exe\b|\brobloxplayerbeta\.exe\b|\broblox\b", "Roblox"),
    (r"\bsteam\.exe\b|steampowered\.com|steamcommunity\.com", "Steam"),
    (r"epicgames|epic games", "Epic Games"),
    (r"league of legends|\bleagueclient\.exe\b|lienminh", "Liên Minh Huyền Thoại"),
    (r"\bvalorant\.exe\b|\bvalorant\b", "Valorant"),
    (r"\bgenshinimpact\.exe\b|genshin impact", "Genshin Impact"),
    (r"\bminecraft\b|javaw\.exe.*minecraft", "Minecraft"),
    (r"free fire|freefire", "Free Fire"),
    (r"bluestacks|\bnox\.exe\b|ldplayer|memu", "Giả lập Android"),
]

DEFAULT_UNSAFE_RULES: List[Tuple[str, str]] = [
    # Web 18+ / Người lớn
    (r"porn|xvideos|xnxx|hentai|\bsex\b|javhd|vlxx|phimsex|loncon|nudity", "Nội dung người lớn 18+"),
    # Cờ bạc, cá cược trực tuyến
    (r"\bbet\b|casino|poker|kubet|shbet|fun88|w88|bk8|fb88|taixiu|tài xỉu|nohu|nổ hũ|baccarat|lode88", "Cờ bạc & Cá cược"),
]

DEFAULT_NEUTRAL_RULES: List[Tuple[str, str]] = [
    (r"explorer\.exe|file explorer|thư mục", "File Explorer"),
    (r"taskmgr\.exe|task manager|trình quản lý tác vụ", "Task Manager"),
    (r"systemsettings\.exe|cài đặt|settings", "Windows Settings"),
    (r"shellexperiencehost\.exe|searchhost\.exe|start menu", "Windows System"),
    (r"ted companion|ted-companion", "Ted Companion"),
    (r"desktop|màn hình nền", "Desktop"),
]

KNOWN_BROWSER_PROCESSES = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
    "coccoc.exe", "opera.exe", "vivaldi.exe", "safari.exe"
}


class ActivityClassifier:
    """Bộ phân loại ngữ cảnh cửa sổ người dùng."""

    def __init__(
        self,
        study_rules: Optional[List[Tuple[str, str]]] = None,
        distraction_rules: Optional[List[Tuple[str, str]]] = None,
        unsafe_rules: Optional[List[Tuple[str, str]]] = None,
        neutral_rules: Optional[List[Tuple[str, str]]] = None,
        search_and_news_rules: Optional[List[Tuple[str, str]]] = None,
    ):
        self._study = study_rules if study_rules is not None else list(DEFAULT_STUDY_RULES)
        self._distraction = distraction_rules if distraction_rules is not None else list(DEFAULT_DISTRACTION_RULES)
        self._unsafe = unsafe_rules if unsafe_rules is not None else list(DEFAULT_UNSAFE_RULES)
        self._neutral = neutral_rules if neutral_rules is not None else list(DEFAULT_NEUTRAL_RULES)
        self._search_and_news = (
            search_and_news_rules if search_and_news_rules is not None else list(DEFAULT_SEARCH_AND_NEWS_RULES)
        )

        # Precompile regex patterns for efficiency
        self._compiled_study = [(re.compile(p, re.IGNORECASE), name) for p, name in self._study]
        self._compiled_distraction = [(re.compile(p, re.IGNORECASE), name) for p, name in self._distraction]
        self._compiled_unsafe = [(re.compile(p, re.IGNORECASE), name) for p, name in self._unsafe]
        self._compiled_neutral = [(re.compile(p, re.IGNORECASE), name) for p, name in self._neutral]
        self._compiled_search_and_news = [(re.compile(p, re.IGNORECASE), name) for p, name in self._search_and_news]

    def classify(self, window_title: str, process_name: str) -> ClassificationResult:
        """Phân loại cửa sổ dựa trên tiêu đề và tên tiến trình."""
        title = (window_title or "").strip()
        proc = (process_name or "").strip().lower()
        combined = f"{proc} {title}".strip()

        is_browser = proc in KNOWN_BROWSER_PROCESSES

        if not combined:
            return ClassificationResult(
                category=ActivityCategory.NEUTRAL,
                app_name="Desktop / Idle",
                is_browser=is_browser
            )

        # 1. Kiểm tra UNSAFE trước tiên (mức độ nghiêm trọng nhất: cờ bạc, 18+)
        for pattern, name in self._compiled_unsafe:
            if pattern.search(combined):
                return ClassificationResult(
                    category=ActivityCategory.UNSAFE,
                    app_name=name,
                    matched_rule=pattern.pattern,
                    is_browser=is_browser,
                    details=f"Phát hiện nội dung không an toàn: '{title}'"
                )

        # 2. Kiểm tra STUDY (Word, Sách mềm, Khan Academy, Google Docs, ChatGPT, GitHub...)
        for pattern, name in self._compiled_study:
            if pattern.search(combined):
                return ClassificationResult(
                    category=ActivityCategory.STUDY,
                    app_name=name,
                    matched_rule=pattern.pattern,
                    is_browser=is_browser,
                    details=f"Ứng dụng học tập & làm việc: {name}"
                )

        # 3. Nếu là trình duyệt: kiểm tra tra cứu (Google/Bing search) hoặc đọc tin tức báo chí
        # Đảm bảo việc tìm kiếm tài liệu (dù có từ khoá như 'youtube', 'zalo') không bị đánh đồng là xao nhãng
        if is_browser:
            for pattern, name in self._compiled_search_and_news:
                if pattern.search(title):
                    return ClassificationResult(
                        category=ActivityCategory.NEUTRAL,
                        app_name=name,
                        matched_rule=pattern.pattern,
                        is_browser=True,
                        details=f"Tra cứu / Đọc tin tức: {title[:60]}"
                    )

        # 4. Kiểm tra DISTRACTION: Chatchit (Zalo, Messenger...) & Mạng xã hội, video, game
        for pattern, name in self._compiled_distraction:
            if pattern.search(combined):
                return ClassificationResult(
                    category=ActivityCategory.DISTRACTION,
                    app_name=name,
                    matched_rule=pattern.pattern,
                    is_browser=is_browser,
                    details=f"Phát hiện xao nhãng: {name}"
                )

        # 5. Kiểm tra NEUTRAL (Hệ thống, Desktop...)
        for pattern, name in self._compiled_neutral:
            if pattern.search(combined):
                return ClassificationResult(
                    category=ActivityCategory.NEUTRAL,
                    app_name=name,
                    matched_rule=pattern.pattern,
                    is_browser=is_browser
                )

        # 6. Mặc định: Nếu là trình duyệt nhưng không khớp bất kỳ xao nhãng nào -> Coi là Duyệt Web bình thường (NEUTRAL)
        # Nguyên tắc cốt lõi: "Không phải tab nào trên web cũng là xao nhãng"
        if is_browser:
            return ClassificationResult(
                category=ActivityCategory.NEUTRAL,
                app_name=f"Web ({proc})",
                is_browser=True,
                details=title[:60]
            )

        # 7. Ứng dụng khác không phân loại được -> Neutral với tên process
        display_proc = proc.replace(".exe", "").capitalize() if proc else "Khác"
        return ClassificationResult(
            category=ActivityCategory.NEUTRAL,
            app_name=display_proc,
            is_browser=False,
            details=title[:60]
        )
