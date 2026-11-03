"""Bộ tri thức ngoại tuyến (Offline Guide Engine) dành cho người dùng mới của Ted Companion.

Ngắn gọn, dễ hiểu cho người dùng phổ thông (không chuyên IT), giải thích các thuật ngữ cốt lõi
ngay cả khi chưa kết nối AI hay mất mạng.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


def _normalize_text(text: str) -> str:
    """Chuẩn hóa chuỗi tiếng Việt: chữ thường, bỏ dấu thanh, loại bỏ ký tự thừa."""
    text = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join([c for c in nfkd if not unicodedata.combining(c)])
    no_accents = no_accents.replace("đ", "d").replace("Đ", "d")
    return re.sub(r"\s+", " ", no_accents)


@dataclass
class OfflineTopic:
    id: str
    title_vi: str
    title_en: str
    keywords: List[str]
    answer_vi: str
    answer_en: str
    suggested_followups: List[str] = field(default_factory=list)


# ==============================================================================
# BỘ CÂU TRẢ LỜI NGẮN GỌN, DỄ HIỂU CHO NGƯỜI DÙNG MỚI (NON-ACADEMIC / GẦN GŨI)
# ==============================================================================

OFFLINE_TOPICS: List[OfflineTopic] = [
    OfflineTopic(
        id="ted_intro",
        title_vi="Ted là ai?",
        title_en="Who is Ted?",
        keywords=[
            "ted", "la ai", "ban la ai", "who are you", "who is ted",
            "gioi thieu", "about", "app nay la gi", "what is this",
            "chao", "chao ted", "alo", "hello", "hi", "hey"
        ],
        answer_vi=(
            "<p>👋 <b>Chào bạn! Mình là Ted — Người bạn nhỏ ở góc màn hình.</b></p>"
            "<p>Mình ở đây để giúp bạn:</p>"
            "<ul>"
            "<li>🍅 <b>Canh giờ làm việc & nghỉ ngơi</b> (Pomodoro 25 phút làm, 5 phút nghỉ).</li>"
            "<li>🅿️ <b>Cất ý tưởng gây phân tâm</b> vào Bãi đỗ để bạn yên tâm làm tiếp.</li>"
            "<li>🎵 <b>Bật tiếng mưa rơi</b> và nhắc nhở nhẹ nhàng khi bạn bị xao nhãng.</li>"
            "</ul>"
            "<p>Dù không có mạng hay chưa kết nối AI, mình vẫn hoạt động 100% trên máy bạn!</p>"
            "<p>👉 <i>Thử gõ: <b>pomodoro</b>, <b>bãi đỗ</b> hoặc <b>chuột</b> để mình chỉ cách dùng nhé!</i></p>"
        ),
        answer_en=(
            "<p>👋 <b>Hi there! I'm Ted — your friendly desktop buddy right at the screen corner.</b></p>"
            "<p>I'm here to help you:</p>"
            "<ul>"
            "<li>🍅 <b>Time your focus and breaks</b> (25 mins work, 5 mins rest).</li>"
            "<li>🅿️ <b>Park sudden distractions</b> so you can stay in flow.</li>"
            "<li>🎵 <b>Play relaxing rain sounds</b> and gently cheer you on.</li>"
            "</ul>"
            "<p>I work 100% offline on your computer without needing internet or AI setup!</p>"
            "<p>👉 <i>Try typing: <b>pomodoro</b>, <b>parking lot</b>, or <b>mouse</b> to learn more!</i></p>"
        ),
        suggested_followups=["pomodoro", "bãi đỗ", "chuột", "deep work"],
    ),
    OfflineTopic(
        id="pomodoro",
        title_vi="Pomodoro (25/5) là gì?",
        title_en="What is Pomodoro (25/5)?",
        keywords=[
            "pomodoro", "ca chua", "qua ca chua", "tomato", "25/5", "25 phut",
            "5 phut", "dem gio", "timer", "nghi ngoi", "break", "cach dung pomodoro"
        ],
        answer_vi=(
            "<p>🍅 <b>Pomodoro rất đơn giản: Chia thời gian làm việc thành từng nhịp ngắn:</b></p>"
            "<ul>"
            "<li><b>25 phút tập trung:</b> Bạn làm đúng 1 việc, không lướt mạng, không sờ điện thoại.</li>"
            "<li><b>5 phút nghỉ ngơi:</b> Ted sẽ rung chuông nhắc bạn đứng dậy vươn vai, uống nước.</li>"
            "<li><b>Cứ 4 nhịp</b> (100 phút làm việc) bạn sẽ được nghỉ dài 15–20 phút.</li>"
            "</ul>"
            "<p>👉 <b>Cách bật:</b> Click chuột phải vào Ted $\rightarrow$ chọn <b>'Bắt đầu Pomodoro'</b>.</p>"
        ),
        answer_en=(
            "<p>🍅 <b>Pomodoro is simple: Split your work into focused bursts:</b></p>"
            "<ul>"
            "<li><b>25-min Focus:</b> Work on one single task without checking your phone.</li>"
            "<li><b>5-min Break:</b> Ted chimes to remind you to stretch and grab water.</li>"
            "<li><b>Every 4 cycles,</b> you earn a longer 15–20 min break.</li>"
            "</ul>"
            "<p>👉 <b>To start:</b> Right-click Ted $\rightarrow$ select <b>'Start Pomodoro'</b>.</p>"
        ),
        suggested_followups=["bãi đỗ", "deep work", "chuột"],
    ),
    OfflineTopic(
        id="parking_lot",
        title_vi="Bãi đỗ xao nhãng là gì?",
        title_en="What is the Parking Lot?",
        keywords=[
            "parking lot", "bai do", "bai do xao nhang", "xao nhang", "distraction",
            "cat y tuong", "park idea", "ghi chu nhanh", "ctrl enter"
        ],
        answer_vi=(
            "<p>🅿️ <b>Bãi đỗ xao nhãng: Nơi cất nhanh ý nghĩ bất chợt để không quên.</b></p>"
            "<p>Đang làm việc mà chợt nhớ: <i>'Tối nay mua đồ'</i> hoặc <i>'Phải gọi cho bạn'</i>? "
            "Nếu đi làm ngay thì hỏng việc chính, còn cố nhớ thì đau đầu.</p>"
            "<p><b>Giải pháp:</b> Nhấn đúp chuột vào Ted $\rightarrow$ gõ việc đó vào ô <b>'Cất nhanh ý tưởng'</b> rồi bấm <b>Enter</b>. "
            "Ted sẽ giữ hộ vào máy cho bạn, hết giờ làm Ted nhắc bạn xem lại!</p>"
        ),
        answer_en=(
            "<p>🅿️ <b>Parking Lot: A quick basket for sudden distracting thoughts.</b></p>"
            "<p>Mid-work, an urgent chore pops into your head? If you do it now, your flow is ruined. If you try to hold it, you get tired.</p>"
            "<p><b>Solution:</b> Double-click Ted $\rightarrow$ type your thought in <b>'Park a distraction idea'</b> and hit <b>Enter</b>. "
            "Ted stores it safely on your computer and reminds you once your timer ends!</p>"
        ),
        suggested_followups=["pomodoro", "deep work", "chuột"],
    ),
    OfflineTopic(
        id="deep_work",
        title_vi="Deep Work là gì?",
        title_en="What is Deep Work?",
        keywords=[
            "deep work", "lam viec sau", "tap trung sau", "flow", "dong tu duy",
            "tap trung", "sieu tap trung"
        ],
        answer_vi=(
            "<p>🎯 <b>Deep Work là làm việc tập trung 100% vào việc quan trọng nhất.</b></p>"
            "<p>Chỉ cần 1 giờ tập trung hoàn toàn (không Facebook, không tin nhắn lắt nhắt), "
            "kết quả làm ra còn nhiều và tốt hơn 4 tiếng vừa làm vừa lướt web. "
            "Ted sinh ra để làm chiếc khiên bảo vệ sự tập trung đó cho bạn!</p>"
        ),
        answer_en=(
            "<p>🎯 <b>Deep Work simply means 100% distraction-free focus on what truly matters.</b></p>"
            "<p>1 hour of real, uninterrupted focus beats 4 hours of multitasking while scrolling social media. "
            "Ted acts as your personal shield to protect this focus time!</p>"
        ),
        suggested_followups=["pomodoro", "bãi đỗ", "eisenhower"],
    ),
    OfflineTopic(
        id="eisenhower",
        title_vi="Ma trận việc (Eisenhower) là gì?",
        title_en="What is the Eisenhower Matrix?",
        keywords=[
            "eisenhower", "ma tran", "matrix", "q1", "q2", "q3", "q4",
            "khan cap", "quan trong", "phan loai"
        ],
        answer_vi=(
            "<p>📊 <b>Ma trận Eisenhower & Các trạng thái công việc với icon trực quan:</b></p>"
            "<p><b>4 Ô Ma trận Eisenhower:</b></p>"
            "<ul>"
            "<li>🔥 <b>Q1 · Làm ngay (Gấp & Quan trọng):</b> Việc cháy nhà, deadline hôm nay $\rightarrow$ Giải quyết ngay!</li>"
            "<li>⭐ <b>Q2 · Lên lịch (Quan trọng, Chưa gấp):</b> Học tập, kỹ năng, việc cốt lõi $\rightarrow$ Đặt lịch Deep Work.</li>"
            "<li>⚡ <b>Q3 · Giao việc (Gấp, Ít quan trọng):</b> Nhờ vả, việc phụ $\rightarrow$ Làm nhanh hoặc nhờ hỗ trợ.</li>"
            "<li>🗑️ <b>Q4 · Loại bỏ (Không gấp, Không quan trọng):</b> Lướt mạng giải trí vô định $\rightarrow$ Cắt giảm.</li>"
            "<li>📥 <b>Chưa phân loại:</b> Ý tưởng mới chưa xếp ô, sẵn sàng kéo thả.</li>"
            "</ul>"
            "<p><b>Trạng thái công việc:</b></p>"
            "<ul>"
            "<li>📋 <b>Chưa làm:</b> Việc đã lên kế hoạch.</li>"
            "<li>▶️ <b>Đang làm:</b> Việc đang chạy trong phiên Pomodoro.</li>"
            "<li>✅ <b>Hoàn thành:</b> Việc đã làm xong!</li>"
            "<li>🅿️ <b>Bãi đỗ:</b> Ý nghĩ xao nhãng cất tạm.</li>"
            "<li>📦 <b>Đã lưu trữ:</b> Việc cũ cất gọn.</li>"
            "</ul>"
            "<p>👉 <i>Click chuột phải lên Ted $\rightarrow$ chọn <b>'Bảng điều khiển'</b> để xem nhé!</i></p>"
        ),
        answer_en=(
            "<p>📊 <b>Eisenhower Matrix & Task Statuses with vivid icons:</b></p>"
            "<p><b>4 Eisenhower Quadrants:</b></p>"
            "<ul>"
            "<li>🔥 <b>Q1 · Do Now (Urgent & Important):</b> Immediate deadlines & fires $\rightarrow$ Handle today!</li>"
            "<li>⭐ <b>Q2 · Schedule (Important, Not Urgent):</b> Deep learning & growth $\rightarrow$ Book Deep Work.</li>"
            "<li>⚡ <b>Q3 · Delegate (Urgent, Less Important):</b> Errands & interruptions $\rightarrow$ Do fast or delegate.</li>"
            "<li>🗑️ <b>Q4 · Eliminate (Neither):</b> Time-wasters & mindless scrolling $\rightarrow$ Cut out.</li>"
            "<li>📥 <b>Unsorted:</b> Fresh incoming items ready to be sorted.</li>"
            "</ul>"
            "<p><b>Task Statuses:</b></p>"
            "<ul>"
            "<li>📋 <b>To do:</b> Planned task ready to start.</li>"
            "<li>▶️ <b>In progress:</b> Active task in a Pomodoro session.</li>"
            "<li>✅ <b>Done:</b> Successfully finished!</li>"
            "<li>🅿️ <b>Parked idea:</b> Stored distraction tangent.</li>"
            "<li>📦 <b>Archived:</b> Closed and tucked away.</li>"
            "</ul>"
            "<p>👉 <i>Right-click Ted $\rightarrow$ select <b>'Dashboard'</b> to inspect!</i></p>"
        ),
        suggested_followups=["deep work", "pomodoro"],
    ),
    OfflineTopic(
        id="hermes_brain",
        title_vi="Não bộ AI là gì?",
        title_en="What is AI Brain?",
        keywords=[
            "hermes", "nao ai", "nao bo", "nao hermes", "brain", "llm", "ai", "ai brain",
            "ket noi", "lap nao", "chua ket noi", "offline"
        ],
        answer_vi=(
            "<p>🧠 <b>Não AI là 'bộ não thông minh' gắn ngoài cho Ted:</b></p>"
            "<ul>"
            "<li><b>Chưa có Não AI:</b> Ted vẫn dùng cực tốt các tính năng: Đếm giờ Pomodoro, Bãi đỗ xao nhãng, Ma trận việc, tiếng mưa và giọng nói. Bạn hoàn toàn không bắt buộc phải cài!</li>"
            "<li><b>Khi kết nối Não AI:</b> Ted sẽ thông minh hơn: Tự xếp việc giúp bạn, tóm tắt email và trò chuyện như chuyên gia.</li>"
            "</ul>"
            "<p>Cứ yên tâm dùng Ted bình thường, khi nào cần AI nâng cao thì lắp sau nhé!</p>"
        ),
        answer_en=(
            "<p>🧠 <b>AI Brain is an optional add-on for Ted:</b></p>"
            "<ul>"
            "<li><b>Without AI Brain:</b> Ted still works wonderfully offline: Pomodoro timer, Parking Lot, Task matrix, rain sounds, and speech. It is not required at all!</li>"
            "<li><b>With AI Brain:</b> Ted gets smarter: Automatically sorts your tasks, summarizes morning emails, and answers complex questions.</li>"
            "</ul>"
            "<p>Feel free to enjoy Ted offline first — you can connect AI later whenever you are ready!</p>"
        ),
        suggested_followups=["pomodoro", "bãi đỗ", "chuột"],
    ),
    OfflineTopic(
        id="mouse_shortcuts",
        title_vi="Cách dùng chuột với Ted",
        title_en="How to use mouse controls with Ted",
        keywords=[
            "chuot", "mouse", "thao tac", "click", "keo", "cach dung",
            "phim tat", "shortcut", "bam"
        ],
        answer_vi=(
            "<p>🖱️ <b>4 Thao tác chuột bỏ túi cực dễ nhớ:</b></p>"
            "<ul>"
            "<li>🐾 <b>Giữ chuột trái kéo:</b> Đưa Ted đến góc nào bạn thích trên màn hình.</li>"
            "<li>💬 <b>Click chuột trái 1 lần:</b> Ted nói 1 câu khích lệ (hoặc bấm để dừng nếu Ted đang nói).</li>"
            "<li>🚀 <b>Click đúp 2 lần:</b> Mở khung chat & Bãi đỗ xao nhãng này.</li>"
            "<li>📋 <b>Click chuột phải:</b> Bật/tắt Pomodoro, tiếng mưa, đổi con vật hoặc mở Bảng điều khiển.</li>"
            "</ul>"
        ),
        answer_en=(
            "<p>🖱️ <b>4 Easy Mouse Moves to Remember:</b></p>"
            "<ul>"
            "<li>🐾 <b>Left-Click Drag:</b> Move Ted to any cozy corner of your screen.</li>"
            "<li>💬 <b>Single Left-Click:</b> Ted speaks an encouraging word (or click to silence if speaking).</li>"
            "<li>🚀 <b>Double-Click:</b> Opens this Chat & Parking Lot window.</li>"
            "<li>📋 <b>Right-Click:</b> Start/stop Pomodoro, rain audio, switch pet, or open Dashboard.</li>"
            "</ul>"
        ),
        suggested_followups=["pomodoro", "bãi đỗ", "nhân vật"],
    ),
    OfflineTopic(
        id="characters",
        title_vi="Các nhân vật bạn đồng hành",
        title_en="Companion Characters",
        keywords=[
            "nhan vat", "character", "pet", "thu cung", "meo", "cu", "gau truc",
            "shiba", "tho", "canh cut", "doi con", "doi nhan vat"
        ],
        answer_vi=(
            "<p>🐾 <b>Ted có 6 người bạn nhỏ cho bạn lựa chọn:</b></p>"
            "<p>🐱 Mèo Ted | 🦉 Cú Đêm | 🐼 Gấu Trúc | 🐕 Cún Shiba | 🐰 Thỏ Bông | 🐧 Cánh Cụt.</p>"
            "<p>👉 <i>Click chuột phải lên pet $\rightarrow$ chọn <b>'Đổi nhân vật'</b> để đổi bạn đồng hành bất cứ lúc nào!</i></p>"
        ),
        answer_en=(
            "<p>🐾 <b>Ted offers 6 cute companions for your workday:</b></p>"
            "<p>🐱 Ted the Cat | 🦉 Night Owl | 🐼 Panda | 🐕 Shiba Inu | 🐰 Bunny | 🐧 Penguin.</p>"
            "<p>👉 <i>Right-click on your pet $\rightarrow$ choose <b>'Switch Character'</b> to change companions anytime!</i></p>"
        ),
        suggested_followups=["chuột", "pomodoro"],
    ),
    OfflineTopic(
        id="quick_start",
        title_vi="Bắt đầu thế nào?",
        title_en="How to get started?",
        keywords=[
            "bat dau", "start", "huong dan", "guide", "nguoi moi", "newbie",
            "lam gi", "how to start", "help", "giup toi"
        ],
        answer_vi=(
            "<p>🚀 <b>Bắt đầu dùng Ted ngay trong 3 bước:</b></p>"
            "<ol>"
            "<li><b>Bước 1:</b> Click chuột phải lên Ted $\rightarrow$ chọn <b>'Bắt đầu Pomodoro'</b> để bật 25 phút tập trung.</li>"
            "<li><b>Bước 2:</b> Tắt Facebook, tập trung làm xong 1 việc.</li>"
            "<li><b>Bước 3:</b> Nếu nảy ra ý nghĩ việc khác, click đúp vào Ted $\rightarrow$ gõ vào ô <b>'Cất nhanh ý tưởng'</b> rồi nhấn Enter. Hết giờ Ted sẽ nhắc bạn xem lại!</li>"
            "</ol>"
            "<p>Đơn giản vậy thôi là bạn đã làm việc cực kỳ hiệu quả rồi đấy!</p>"
        ),
        answer_en=(
            "<p>🚀 <b>Start using Ted in 3 simple steps:</b></p>"
            "<ol>"
            "<li><b>Step 1:</b> Right-click Ted $\rightarrow$ choose <b>'Start Pomodoro'</b> for a 25-min focus sprint.</li>"
            "<li><b>Step 2:</b> Put away phone and finish your priority task.</li>"
            "<li><b>Step 3:</b> Distraction popped up? Double-click Ted $\rightarrow$ type it into <b>'Park a distraction'</b> and hit Enter!</li>"
            "</ol>"
            "<p>That's all it takes to double your daily productivity!</p>"
        ),
        suggested_followups=["pomodoro", "bãi đỗ", "chuột"],
    ),
]


# ==============================================================================
# HÀM MATCHING & GỢI Ý
# ==============================================================================

def match_offline_guide(user_text: str, lang: str = "vi") -> Optional[Tuple[OfflineTopic, str]]:
    """
    So khớp câu hỏi với bộ tri thức ngắn gọn ngoại tuyến.
    Trả về (topic, answer_html) hoặc None nếu không khớp.
    """
    if not user_text or not user_text.strip():
        return None

    clean_text = _normalize_text(user_text)

    best_topic: Optional[OfflineTopic] = None
    best_score = 0

    for topic in OFFLINE_TOPICS:
        score = 0
        for kw in topic.keywords:
            clean_kw = _normalize_text(kw)
            if clean_kw == clean_text:
                score += 100
            elif f" {clean_kw} " in f" {clean_text} ":
                score += len(clean_kw.split()) * 20
            elif clean_text.startswith(clean_kw) or clean_text.endswith(clean_kw):
                score += len(clean_kw.split()) * 15
            elif clean_kw in clean_text:
                score += len(clean_kw.split()) * 10

        if score > best_score:
            best_score = score
            best_topic = topic

    if best_topic and best_score >= 10:
        answer = best_topic.answer_vi if lang == "vi" else best_topic.answer_en
        return best_topic, answer

    return None


def get_offline_starter_menu(lang: str = "vi") -> str:
    """Menu trợ giúp ngắn gọn khi người dùng gõ câu bất kỳ mà offline / chưa kết nối AI."""
    if lang == "vi":
        return (
            "<p>🌱 <b>Chào bạn! Ted đang chạy chế độ Ngoại tuyến (chưa kết nối AI).</b></p>"
            "<p>Bạn vẫn có thể dùng ngay các tính năng chính mà không cần mạng:</p>"
            "<ul>"
            "<li>🍅 <b>Bấm giờ Pomodoro 25 phút</b> (Click chuột phải $\rightarrow$ Bắt đầu Pomodoro).</li>"
            "<li>🅿️ <b>Cất ý tưởng xao nhãng</b> (Gõ vào ô bên dưới rồi nhấn Enter).</li>"
            "</ul>"
            "<p>❓ <b>Gõ một từ để mình giải thích nhanh:</b></p>"
            "<p>👉 <code>bắt đầu</code> | <code>pomodoro</code> | <code>bãi đỗ</code> | <code>deep work</code> | <code>chuột</code> | <code>não ai</code></p>"
        )
    return (
        "<p>🌱 <b>Hi! Ted is running in Offline Mode (no AI connection).</b></p>"
        "<p>You can still use all core tools right now without internet:</p>"
        "<ul>"
        "<li>🍅 <b>25-min Pomodoro timer</b> (Right-click $\rightarrow$ Start Pomodoro).</li>"
        "<li>🅿️ <b>Park distractions</b> (Type in the box below and press Enter).</li>"
        "</ul>"
        "<p>❓ <b>Type a keyword for a quick explanation:</b></p>"
        "<p>👉 <code>start</code> | <code>pomodoro</code> | <code>parking lot</code> | <code>deep work</code> | <code>mouse</code> | <code>ai brain</code></p>"
    )


# Mẹo ngắn gọn cho người mới khi click chuột vào Pet
NEWBIE_TIPS_VI: List[str] = [
    "💡 Mẹo nhỏ: Bấm phím Enter ở ô Bãi đỗ để cất nhanh suy nghĩ xao nhãng nhé!",
    "🍅 Pomodoro chuẩn là 25 phút làm việc và 5 phút nghỉ ngơi vươn vai.",
    "🎯 Deep Work: Làm 1 việc trong 1 thời điểm hiệu quả hơn gấp nhiều lần đa nhiệm.",
    "🖱️ Kéo chuột trái để đưa Ted đến góc màn hình bạn thấy dễ chịu nhất.",
    "🌧️ Bạn có thể bật tiếng mưa rơi bằng cách click chuột phải vào Ted.",
    "⭐ Click chuột phải để đổi sang bạn Cú Đêm, Gấu Trúc hay Cún Shiba bất cứ lúc nào!",
]

NEWBIE_TIPS_EN: List[str] = [
    "💡 Quick tip: Hit Enter in the Parking Lot box to instantly save sudden thoughts!",
    "🍅 A standard Pomodoro is 25 minutes of focus followed by a 5-minute stretch.",
    "🎯 Deep Work: Singular focus produces far better work than frantic multitasking.",
    "🖱️ Drag with your left mouse button to place Ted in any comfortable corner.",
    "🌧️ You can turn on relaxing rain sounds by right-clicking on Ted.",
    "⭐ Right-click to switch to Night Owl, Panda, or Shiba whenever you like!",
]
