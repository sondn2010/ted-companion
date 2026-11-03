"""Nội dung cẩm nang Trợ giúp (Tiếng Việt) dạng HTML — CSS áp từ dashboard_help_tab_widget.py."""

HELP_HTML_VI = r"""
<h1>🐾 Cẩm Nang &amp; Tra Cứu Thuật Ngữ Ted Companion</h1>
<p>Chào mừng bạn đến với <strong>Ted Companion</strong> — người bạn đồng hành ảo sống ngay trên màn hình máy tính của bạn, giúp bạn duy trì trạng thái <strong>Deep Work (Làm việc sâu)</strong>, vượt qua xao nhãng và kết nối thông minh với não bộ <strong>Não AI</strong>.</p>
<p>Tài liệu này được biên soạn để giải thích toàn bộ triết lý, tính năng và thuật ngữ xuất hiện trong ứng dụng.</p>
<hr />
<h2><a name="sec1"></a>📑 Mục Lục</h2>
<ol>
<li><a href="#sec2">Triết Lý &amp; Kiến Trúc Tổng Quan</a></li>
<li><a href="#sec5">Nhân Vật Đồng Hành (Chibi Skins) &amp; Âm Thanh Ambient</a></li>
<li><a href="#sec9">Bộ Đếm Deep Work &amp; Chu Kỳ Pomodoro</a></li>
<li><a href="#sec14">Nhắc Nhở Chánh Niệm (Mindful Pings) &amp; Lời Nhắc Chủ Động</a></li>
<li><a href="#sec17">Bãi Đỗ Xao Nhãng (Parking Lot) &amp; Trút Bỏ Tư Duy (Brain Dump)</a></li>
<li><a href="#sec21">Não Bộ Trí Tuệ Nhân Tạo (Não AI (Cloud / VPS))</a></li>
<li><a href="#sec26">Hệ Thống Module Chuyên Sâu (Modular Architecture)</a>
<ul>
<li><a href="#sec27">Module Công Việc (Work Assistant)</a></li>
<li><a href="#sec28">Module Học Tập &amp; Gia Sư (Learning Coach &amp; SRS)</a></li>
</ul>
</li>
<li><a href="#sec29">Bảng Điều Khiển (Dashboard) &amp; Lưu Trữ Linh Hoạt (Hybrid: Local Cache + Cloud/VPS Brain)</a></li>
<li><a href="#sec30">Thao Tác Chuột, Bong Bóng Thoại &amp; Phím Tắt</a></li>
<li><a href="#sec35">Hub, Họp, Gỡ Rối &amp; Phím Tắt Toàn Cục</a></li>
<li><a href="#sec34">Bảng Tra Cứu Thuật Ngữ A–Z (Glossary)</a></li>
</ol>
<hr />
<h2><a name="sec2"></a>1. Triết Lý &amp; Kiến Trúc Tổng Quan</h2>
<h3><a name="sec3"></a>1.1. Triết lý thiết kế</h3>
<ul>
<li><strong>Non-intrusive (Không xâm phạm):</strong> Ted không can thiệp sâu vào quyền riêng tư (không chụp màn hình ngầm, không quét ứng dụng đang mở). Ted đồng hành bằng sự thấu hiểu, chánh niệm và các nhịp nhắc nhở tôn trọng sự tập trung của bạn.</li>
<li><strong>Cozy &amp; Friendly (Ấm áp, không phán xét):</strong> Nếu bạn xao nhãng, Ted không trừng phạt hay cảnh báo gắt gỏng mà nhẹ nhàng hỗ trợ bạn ghi nhận và quay lại dòng chảy làm việc.</li>
<li><strong>Kiến trúc Hybrid (Bộ đệm cục bộ &amp; Não bộ Cloud/VPS):</strong> Ted kết hợp hài hòa giữa tốc độ phản hồi tức thì và sự bền vững của dữ liệu dài hạn:
<ul>
<li><strong>Local-First Cache:</strong> Các thao tác công việc hàng ngày, bảng điều khiển và bộ đếm thời gian được đệm trong SQLite trên máy tính của bạn, hoạt động siêu mượt ngay cả khi không có mạng Internet.</li>
<li><strong>Hỗ trợ Brain trên Cloud / VPS:</strong> Não bộ AI (Não AI) <strong>hoàn toàn không bắt buộc phải lưu trữ cục bộ</strong>. Bạn có thể đặt Brain trên máy chủ đám mây (VPS Cloud 24/7), giúp lưu trữ an toàn ký ức dài hạn, tài liệu dự án, tiến độ học tập và đồng bộ xuyên suốt đa thiết bị mà không chiếm dụng tài nguyên hay phụ thuộc vào máy tính cá nhân.</li>
</ul>
</li>
</ul>
<h3><a name="sec4"></a>1.2. Kiến trúc 2 tầng (Two-Tier Architecture)</h3>
<ul>
<li><strong>Tầng Giao Diện (Ted Desktop Client - PySide6):</strong> Là &quot;thể xác&quot; hiển thị nhân vật hoạt họa trong suốt nổi trên màn hình, chạy bộ đếm thời gian, phát âm thanh thư giãn và cung cấp Bảng điều khiển quản trị.</li>
<li><strong>Tầng Trí Tuệ (Não AI (Cloud / VPS)):</strong> Là &quot;não bộ&quot; có thể chạy linh hoạt trên máy chủ riêng (VPS / Cloud 24/7) hoặc trên máy cục bộ (Local). Não AI đảm nhận việc bóc tách mục tiêu, ghi nhớ thói quen dài hạn (<code>memories/</code>), phân tích câu hỏi và trò chuyện qua giao thức mạng.</li>
</ul>
<hr />
<h2><a name="sec5"></a>2. Nhân Vật Đồng Hành (Chibi Skins) &amp; Âm Thanh Ambient</h2>
<h3><a name="sec6"></a>2.1. Danh mục 6 nhân vật Chibi</h3>
<p>Ứng dụng cung cấp 6 người bạn nhỏ với phong cách hoạt họa SVG sắc nét, chuyển đổi mượt mà theo trạng thái:</p>
<ol>
<li><strong>🐱 Mèo Ted (<code>cat</code>):</strong> Bạn mèo tinh nghịch, ấm áp, chăm chỉ gõ bàn phím cùng bạn.</li>
<li><strong>🐕 Cún Shiba (<code>shiba</code>):</strong> Bạn cún trung thành, vui tươi, luôn cổ vũ tinh thần.</li>
<li><strong>🐰 Thỏ Bông (<code>bunny</code>):</strong> Bạn thỏ dịu dàng, đem lại cảm giác yên bình, tĩnh lặng.</li>
<li><strong>🐧 Cánh Cụt (<code>penguin</code>):</strong> Bạn cánh cụt ngăn nắp, biểu tượng của sự kỷ luật và kiên định.</li>
<li><strong>🦉 Cú Đêm (<code>owl</code>):</strong> Bạn cú thông thái, hoàn hảo cho những phiên làm việc đêm khuya.</li>
<li><strong>🐼 Gấu Trúc (<code>panda</code>):</strong> Bạn gấu trúc điềm đạm, giúp giảm căng thẳng và áp lực.</li>
</ol>
<h3><a name="sec7"></a>2.2. Các trạng thái hoạt ảnh (Pet Animations)</h3>
<ul>
<li><code>IDLE</code>: Nhân vật thư giãn, thỉnh thoảng chớp mắt, đọc sách khi bạn chưa bắt đầu làm việc.</li>
<li><code>FOCUSING</code>: Nhân vật đeo tai nghe, gõ phím hoặc tập trung cao độ cùng bạn trong phiên Deep Work.</li>
<li><code>NUDGING</code>: Nhân vật giơ bảng hoặc khẽ vẫy tay khi cần nhắc nhở bạn.</li>
<li><code>CELEBRATING</code>: Nhân vật vẫy cờ, reo vui khi bạn hoàn thành một phiên làm việc.</li>
<li><code>SLEEPING</code>: Nhân vật cuộn tròn ngủ khi chuyển sang chế độ nghỉ ngơi.</li>
</ul>
<h3><a name="sec8"></a>2.3. Âm thanh nền (Ambient Sound)</h3>
<ul>
<li><strong>Tiếng mưa rơi (Rainfall Audio):</strong> Âm thanh tiếng mưa lặp vô tận (Looping) giúp che bớt tiếng ồn ngoại cảnh (White Noise), đưa não bộ vào trạng thái sóng não Alpha để tập trung sâu.</li>
<li><strong>Chuông chánh niệm (Mindful Chimes):</strong> Âm thanh chuông gió nhẹ nhàng báo hiệu khi hết giờ hoặc khi có nhịp kiểm tra tập trung, không gây giật mình.</li>
</ul>
<hr />
<h2><a name="sec9"></a>3. Bộ Đếm Deep Work &amp; Chu Kỳ Pomodoro</h2>
<h3><a name="sec10"></a>3.1. Deep Work (Làm việc sâu)</h3>
<p>Thuật ngữ chỉ trạng thái tập trung cao độ, không bị phân tán tư tưởng vào những việc vụn vặt, giúp giải quyết các bài toán hóc búa và tạo ra giá trị đột phá trong thời gian ngắn nhất.</p>
<h3><a name="sec11"></a>3.2. Kỹ thuật Pomodoro</h3>
<p>Phương pháp quản lý thời gian chia nhỏ phiên làm việc:</p>
<ul>
<li><strong>Phiên tập trung (Focus Session):</strong> Mặc định 25 phút (có thể tùy chỉnh từ 15–60 phút trong Cài đặt).</li>
<li><strong>Nghỉ ngắn (Short Break):</strong> Mặc định 5 phút để đứng dậy uống nước, vươn vai thư giãn mắt.</li>
<li><strong>Nghỉ dài (Long Break):</strong> Sau mỗi 4 chu kỳ Pomodoro, dành 15–30 phút nghỉ ngơi nạp lại năng lượng.</li>
</ul>
<h3><a name="sec12"></a>3.3. Khóa mục tiêu (Intent Locking)</h3>
<p>Khi bạn bấm bắt đầu một phiên Deep Work, Ted sẽ đề nghị bạn xác định rõ: <em>&quot;Trong phiên này, kết quả cụ thể duy nhất bạn muốn hoàn thành là gì?&quot;</em>. Việc xác định một mục tiêu duy nhất giúp não bộ tránh lan man sang nhiều việc cùng lúc.</p>
<h3><a name="sec13"></a>3.4. Đánh giá phiên (Session Review)</h3>
<p>Kết thúc phiên, Ted chúc mừng và cho phép bạn chấm điểm độ tập trung (1–5 sao) kèm ghi chú ngắn. Dữ liệu này được thống kê trên biểu đồ Analytics để bạn theo dõi xu hướng làm việc qua từng tuần.</p>
<hr />
<h2><a name="sec14"></a>4. Nhắc Nhở Chánh Niệm (Mindful Pings) &amp; Lời Nhắc Chủ Động</h2>
<h3><a name="sec15"></a>4.1. Vòng lặp Chánh niệm (Mindful Ping)</h3>
<ul>
<li>Cứ sau mỗi 15 hoặc 20 phút trong phiên làm việc, Ted phát một tiếng chuông khẽ và hiện câu hỏi: <em>&quot;Bạn vẫn đang tập trung vào [Tên công việc] chứ?&quot;</em>.</li>
<li><strong>Phản hồi 1 chạm:</strong>
<ul>
<li>Bấm <code>[👍 Vẫn đang tập trung]</code>: Ted vui vẻ lui về góc màn hình (hoặc tự ẩn sau 8 giây nếu bạn đang gõ phím liên tục).</li>
<li>Bấm <code>[😅 Mình hơi xao nhãng]</code>: Ted ghi nhận số lần xao nhãng và động viên bạn hít sâu quay lại công việc.</li>
</ul>
</li>
</ul>
<h3><a name="sec16"></a>4.2. Lời nhắc chủ động (Proactive Nudges)</h3>
<p>Não AI kết nối từ xa có thể chủ động gửi các thông báo quan trọng về Ted (ví dụ: <em>&quot;Còn 10 phút nữa đến cuộc họp Kế hoạch Tuần&quot;</em> hoặc <em>&quot;Hôm nay bạn có 2 mục tiêu lớn (Rocks) cần cập nhật tiến độ&quot;</em>).</p>
<hr />
<h2><a name="sec17"></a>5. Bãi Đỗ Xao Nhãng (Parking Lot) &amp; Trút Bỏ Tư Duy (Brain Dump)</h2>
<h3><a name="sec18"></a>5.1. Vấn đề &quot;Bong bóng ý tưởng bất chợt&quot;</h3>
<p>Khi đang tập trung viết code hoặc soạn tài liệu, bạn chợt nhớ ra: <em>&quot;Quên chưa gửi email cho đối tác&quot;</em>, hoặc nảy ra ý tưởng <em>&quot;Nên tìm hiểu thử thư viện X&quot;</em>. Nếu lập tức chuyển tab để làm, bạn sẽ mất từ 15–20 phút để lấy lại mạch tư duy ban đầu.</p>
<h3><a name="sec19"></a>5.2. Giải pháp Bãi đỗ (Distraction Parking Lot)</h3>
<p>Bãi đỗ là nơi lưu trữ tạm các ý tưởng bất chợt đó. Bạn chỉ cần:</p>
<ol>
<li>Click vào nhân vật Ted để mở bong bóng chat nhỏ (hoặc click đúp / phím tắt để mở trang 💬 Trò chuyện trong app).</li>
<li>Gõ ý tưởng và bấm <strong><code>🅿️ Bãi đỗ</code> (Ctrl + Enter)</strong>.</li>
<li>Ý tưởng được cất ngay vào danh sách chờ trong Database. Bạn yên tâm làm tiếp phiên Deep Work mà không sợ bị quên.</li>
</ol>
<h3><a name="sec20"></a>5.3. Trút bỏ tư duy &amp; Trò chuyện (Brain Dump &amp; Quick Chat)</h3>
<ul>
<li>Gõ nội dung và bấm <strong><code>💬 Chat</code> (Enter)</strong>: Gửi câu hỏi hoặc dòng suy nghĩ của bạn trực tiếp cho Não AI. Ted sẽ trả lời tức thì dưới dạng văn bản trực tiếp trong bong bóng.</li>
<li>Phím <strong><code>Esc</code></strong>: Đóng nhanh bong bóng trò chuyện.</li>
</ul>
<hr />
<h2><a name="sec21"></a>6. Não Bộ Trí Tuệ Nhân Tạo (Não AI (Cloud / VPS))</h2>
<h3><a name="sec22"></a>6.1. Não AI là gì?</h3>
<p><strong>Não AI</strong> là nền tảng AI Agent tự hành có khả năng ghi nhớ dài hạn, lập kế hoạch và sử dụng công cụ qua máy chủ mạng.</p>
<h3><a name="sec23"></a>6.2. Vận hành Não bộ trên VPS / Cloud và Local (Không ép buộc lưu trữ cục bộ)</h3>
<p>Hệ thống được thiết kế mở để bạn linh hoạt chọn nơi lưu trữ và chạy &quot;Não bộ&quot; (Brain):</p>
<ul>
<li><strong>VPS / Cloud Mode (24/7 - Khuyên dùng):</strong>
<ul>
<li><strong>Lưu trữ đám mây bền vững:</strong> Toàn bộ ký ức dài hạn (<code>memories/MEMORY.md</code>, <code>USER.md</code>), tri thức tài liệu (<code>knowledge/</code>), tính cách (<code>SOUL.md</code>) và các kỹ năng chuyên biệt (<code>skills/</code>) được lưu trữ trực tiếp trên máy chủ VPS đám mây riêng của bạn.</li>
<li><strong>Không phụ thuộc máy trạm:</strong> Bạn hoàn toàn <strong>không cần phải lưu trữ toàn bộ dữ liệu trên máy tính cục bộ</strong>. Khi bạn tắt máy tính hay đi công tác, Brain trên VPS vẫn hoạt động bền bỉ 24/7, duy trì trạng thái và sẵn sàng phục vụ khi bạn kết nối lại từ bất kỳ thiết bị nào.</li>
<li><strong>Đa thiết bị &amp; Dùng chung trong gia đình:</strong> Một máy chủ VPS có thể host nhiều profile riêng biệt (bố mẹ, con cái: <code>family_work</code>, <code>family_thcs</code>, <code>family_duhoc</code>, <code>family_caohoc</code>), vừa đảm bảo an toàn riêng tư vừa quản trị tập trung.</li>
<li><strong>Chủ động 24/7:</strong> Brain có thể liên tục theo dõi lịch Google Calendar, gửi lời nhắc chủ động (Proactive Nudge) và chuẩn bị kế hoạch công việc/học tập trước khi bạn bắt đầu ngày mới.</li>
</ul>
</li>
<li><strong>Local Mode:</strong> Dành cho người dùng muốn cô lập hoàn toàn hệ thống offline trên một máy tính cá nhân duy nhất (chạy Não AI tại <code>http://localhost:8000</code>).</li>
</ul>
<h3><a name="sec24"></a>6.3. FastMCP Server (Model Context Protocol)</h3>
<p>Ted tích hợp một máy chủ FastMCP Server nội bộ. Nhờ đó, Não AI có thể &quot;gọi ngược&quot; về Ted để thực thi các tác vụ thực tế:</p>
<ul>
<li>Bắt đầu hoặc kết thúc phiên Pomodoro.</li>
<li>Tự động thêm công việc mới vào danh sách.</li>
<li>Ghi chép nhật ký công việc.</li>
<li>Đổi biểu cảm và trạng thái của linh vật Ted.</li>
</ul>
<h3><a name="sec25"></a>6.4. Đa hồ sơ chuyên biệt (Multi-Profiles)</h3>
<p>Ứng dụng hỗ trợ kết nối đồng thời với các hồ sơ Não AI độc lập để phục vụ nhiều thành viên hoặc nhiều mục đích trong gia đình:</p>
<ul>
<li><code>family_work</code>: Hồ sơ trợ lý công việc chuyên nghiệp cho phụ huynh.</li>
<li><code>thcs</code>: Hồ sơ trợ giảng học tập bám sát chương trình THCS (Toán, Văn, Anh).</li>
<li><code>duhoc</code>: Hồ sơ cố vấn lộ trình chuẩn bị hồ sơ du học.</li>
<li><code>caohoc</code>: Hồ sơ trợ lý nghiên cứu và ôn thi cao học.</li>
</ul>
<hr />
<h2><a name="sec26"></a>7. Hệ Thống Module Chuyên Sâu (Modular Architecture)</h2>
<p>Ted được thiết kế theo kiến trúc module cắm rút (Plug-and-play). Bạn có thể bật/tắt từng module trong tab Cài đặt:</p>
<h3><a name="sec27"></a>7.1. Module Công Việc (Work Assistant)</h3>
<p>Dành cho người đi làm và quản lý dự án:</p>
<ul>
<li><strong>Tảng Đá Lớn (Rocks):</strong> Lấy cảm hứng từ phương pháp quản trị OKR. Mỗi quý hoặc mỗi tháng, bạn chỉ nên có từ 3 đến 5 &quot;Tảng đá lớn&quot; (nhiệm vụ chiến lược trọng yếu). Ted giúp bạn luôn giữ những tảng đá này ở vị trí ưu tiên cao nhất trước khi bị những &quot;viên sỏi&quot; (việc vặt) lấp đầy thời gian.</li>
<li><strong>Tóm tắt đầu ngày (Morning Briefing):</strong> Cung cấp bức tranh tổng thể về các cuộc họp, deadline và mục tiêu quan trọng cần giải quyết trong ngày.</li>
<li><strong>Đồng bộ Lịch &amp; Nhắc họp (Calendar Cache &amp; Meeting Alerts):</strong> Kết nối với Google Calendar hoặc Outlook để phát tín hiệu nhắc nhở trước giờ họp 5–10 phút mà không làm ngắt mạch tư duy đột ngột.</li>
</ul>
<h3><a name="sec28"></a>7.2. Module Học Tập &amp; Gia Sư (Learning Coach &amp; SRS)</h3>
<p>Dành cho học sinh, sinh viên và người tự học:</p>
<ul>
<li><strong>Spaced Repetition System (SRS - Lặp lại ngắt quãng):</strong> Phương pháp khoa học chứng minh việc ôn lại kiến thức vào đúng thời điểm chuẩn bị quên sẽ giúp thông tin khắc sâu vào trí nhớ dài hạn.</li>
<li><strong>Hộp Leitner 5 Ngăn (5 Leitner Boxes):</strong>
<ul>
<li><strong>Hộp 1:</strong> Thẻ mới học hoặc trả lời sai — Ôn tập hàng ngày.</li>
<li><strong>Hộp 2:</strong> Trả lời đúng lần 1 — Ôn tập sau mỗi 2 ngày.</li>
<li><strong>Hộp 3:</strong> Trả lời đúng lần 2 — Ôn tập sau mỗi 4 ngày.</li>
<li><strong>Hộp 4:</strong> Trả lời đúng lần 3 — Ôn tập sau mỗi 7 ngày.</li>
<li><strong>Hộp 5:</strong> Đã thành thục — Ôn tập sau mỗi 14–30 ngày.</li>
<li><em>Quy tắc vàng:</em> Trả lời đúng, thẻ được thăng lên hộp cao hơn; trả lời sai lập tức rơi về Hộp 1 để củng cố lại.</li>
</ul>
</li>
<li><strong>Các hình thức ôn tập đa dạng:</strong>
<ul>
<li><code>Quiz</code>: Trắc nghiệm 4 đáp án có giải thích chi tiết.</li>
<li><code>Flashcard</code>: Thẻ ghi nhớ 2 mặt (Thuật ngữ / Định nghĩa).</li>
<li><code>Step-by-step</code>: Hướng dẫn giải từng bước cho bài toán phức tạp.</li>
<li><code>Writing</code>: Bài tập luyện viết luận có AI chấm và sửa lỗi hành văn.</li>
</ul>
</li>
<li><strong>Cột mốc &amp; Báo cáo (Milestones &amp; Progress):</strong> Thống kê số lượng thẻ đã học, tỷ lệ thành thạo và xuất báo cáo cho phụ huynh/giáo viên.</li>
</ul>
<hr />
<h2><a name="sec29"></a>8. Bảng Điều Khiển (Dashboard) &amp; Lưu Trữ Linh Hoạt (Hybrid: Local Cache + Cloud/VPS Brain)</h2>
<p>Ted áp dụng mô hình lưu trữ kết hợp thông minh (Hybrid Architecture):</p>
<ul>
<li><strong>Local Cache (Bộ đệm cục bộ):</strong> Đảm bảo giao diện máy trạm (Desktop Client) mở tức thì, kéo thả công việc mượt mà và hoạt động trơn tru cả khi mất kết nối mạng.</li>
<li><strong>Cloud / VPS Brain (Lưu trữ trí tuệ đám mây):</strong> Lưu giữ tri thức dài hạn, nhật ký quyết định, tiến trình học tập và đồng bộ hóa đa thiết bị. Bạn hoàn toàn không bị bó buộc vào lưu trữ cục bộ của một máy tính đơn lẻ.</li>
</ul>
<p>Nhấp chuột phải vào Ted và chọn <strong>📋 Trung tâm quản lý</strong> để mở Dashboard:</p>
<ul>
<li><strong>Tab Công việc &amp; Bãi đỗ (Tasks):</strong> Quản lý danh sách việc cần làm (<code>Todo</code>, <code>Doing</code>, <code>Done</code>) và bốc các việc từ Bãi đỗ xao nhãng sang hàng đợi thực thi.</li>
<li><strong>Tab Nhật ký Ngày (Daily Journal):</strong> Không gian phản tư cuối ngày (Daily Reflection) để ghi nhận những điều đã hoàn thành, bài học kinh nghiệm và cảm xúc cá nhân.</li>
<li><strong>Tab Phân tích Tập trung (Analytics):</strong> Biểu đồ hiển thị tổng thời lượng Deep Work trong ngày/tuần, số phiên hoàn thành và tỷ lệ duy trì chánh niệm.</li>
<li><strong>Tab Trợ giúp (Help):</strong> Nơi bạn đang đọc tài liệu này! Nội dung hiển thị theo ngôn ngữ đang chọn (Việt / Anh) và hỗ trợ tìm kiếm từ khóa.</li>
<li><strong>Tab Cài đặt (Settings):</strong> Cấu hình thời gian Pomodoro, lựa chọn linh vật, kết nối máy chủ Não AI (chạy Local hoặc VPS Cloud) và quản lý các Module.</li>
</ul>
<hr />
<h2><a name="sec30"></a>9. Thao Tác Chuột, Bong Bóng Thoại &amp; Phím Tắt</h2>
<table width="100%" cellspacing="0" cellpadding="8">
<thead>
<tr>
<th>Thao tác</th>
<th>Vị trí thực hiện</th>
<th>Hành động tương ứng</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Click đơn (Left Click)</strong></td>
<td>Trên thân nhân vật Ted</td>
<td>Mở bong bóng chat nhỏ &amp; Bãi đỗ; dòng đầu là câu động viên kèm việc đang làm / việc khẩn cấp.</td>
</tr>
<tr>
<td><strong>Click đúp (Double Click)</strong></td>
<td>Trên thân nhân vật Ted</td>
<td>Mở trang <strong>💬 Trò chuyện</strong> to trong app (dễ đọc hơn).</td>
</tr>
<tr>
<td><strong>Kéo giữ chuột trái</strong></td>
<td>Trên thân nhân vật Ted</td>
<td>Di chuyển nhân vật đến vị trí bất kỳ trên màn hình.</td>
</tr>
<tr>
<td><strong>Click chuột phải</strong></td>
<td>Trên thân nhân vật Ted</td>
<td>Mở Menu ngữ cảnh (Pomodoro, Đổi skin, Âm thanh, Dashboard, Cài đặt, Trợ giúp).</td>
</tr>
<tr>
<td><strong>Click chuột trái / phải</strong></td>
<td>Biểu tượng trên Khay hệ thống</td>
<td>Hiện/Ẩn Ted, mở nhanh Dashboard, Bắt đầu Pomodoro, Thoát ứng dụng.</td>
</tr>
<tr>
<td><strong>Phím Enter</strong></td>
<td>Trong ô nhập bong bóng</td>
<td>Gửi tin nhắn trò chuyện với Não AI (<code>💬 Chat</code>).</td>
</tr>
<tr>
<td><strong>Phím Ctrl + Enter</strong></td>
<td>Trong ô nhập bong bóng</td>
<td>Cất nhanh nội dung vào Bãi đỗ xao nhãng (<code>🅿️ Bãi đỗ</code>).</td>
</tr>
<tr>
<td><strong>Phím Esc</strong></td>
<td>Trong ô nhập bong bóng</td>
<td>Đóng ngay bong bóng thoại.</td>
</tr>
<tr>
<td><strong>🤫 Click nhanh 5 lần</strong></td>
<td>Trên thân nhân vật</td>
<td><strong>Hành động ẩn:</strong> mở popup <strong>🎭 Cá tính nhân vật</strong> (tên riêng, tính cách, giọng nói riêng).</td>
</tr>
</tbody>
</table>
<h3><a name="sec31"></a>9.1. 🤫 Các hành động ẩn (dễ quên — ghi lại ở đây)</h3>
<table width="100%" cellspacing="0" cellpadding="8">
<thead>
<tr>
<th>Hành động ẩn</th>
<th>Cách làm</th>
<th>Ghi chú</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>🎭 Cá tính nhân vật</strong></td>
<td>Click <strong>nhanh 5 lần liên tiếp</strong> lên nhân vật</td>
<td>Mỗi nhân vật (Mèo, Cú, Gấu Trúc, Shiba, Thỏ, Cánh Cụt) có <strong>tên riêng</strong>, <strong>tính cách</strong> (Vui vẻ, Điềm tĩnh, Năng động, Dễ thương, Hài hước, Nghiêm túc) và <strong>giọng đọc riêng</strong> (giọng máy chủ / giọng offline / tốc độ). Bấm <strong>🔊 Nghe thử</strong> rồi <strong>💾 Lưu</strong>. <strong>↺ Về mặc định</strong> để bỏ cấu hình.</td>
</tr>
<tr>
<td>Click đúp</td>
<td>Click 2 lần</td>
<td>Vì có cử chỉ 5 lần, chat mở sau một nhịp ngắn (~0,5 giây) để app biết bạn có click tiếp hay không.</td>
</tr>
</tbody>
</table>
<blockquote>
<p>Cá tính nhân vật <strong>chỉ là cấu hình phía app</strong>: đổi tên hiển thị, câu cửa miệng khi click đơn và giọng TTS. <strong>Không đổi prompt hệ thống</strong> — nội dung trò chuyện vẫn do Não AI quyết định.</p>
</blockquote>
<h3><a name="sec32"></a>9.2. 🔊 Giọng nói (TTS) &amp; 🎙️ Nhận giọng nói (STT) — tải mô hình ngay trong app</h3>
<ul>
<li>Bộ cài <strong>không kèm mô hình giọng nói</strong> để nhẹ. Vào <strong>Dashboard → ⚙️ Cài đặt → Giọng nói / Nhận giọng nói</strong>:
<ol>
<li>Bấm <strong>✨ Chọn cấu hình mẫu…</strong> → popup có <strong>ô tìm kiếm</strong> (gõ không dấu: <code>cham</code>, <code>nu</code>, <code>offline</code>, <code>tieng anh</code>, <code>may yeu</code>…) với hơn 20 mẫu → <strong>Điền vào cấu hình</strong>: app tự điền mọi ô.</li>
<li>Mẫu offline mà chưa có mô hình → app hỏi <strong>tải ngay</strong>. Hoặc bấm <strong>⬇️ Tải / quản lý giọng đọc offline…</strong> để chọn mô hình (xem dung lượng, chất lượng ⭐ khuyên dùng).</li>
<li>Tải xong app <strong>tự chuyển sang “Trên máy (offline)”</strong> và chọn sẵn mô hình → bấm <strong>Nghe thử / Chạy thử</strong> → <strong>💾 Lưu cấu hình giọng nói</strong>.</li>
</ol>
</li>
<li>Mô hình lưu ở <code>~/.ted/voice_models/</code>, xoá được ngay trong popup tải. Lần tải đầu tiên app tải kèm bộ chạy nhỏ (Piper ~22MB, whisper.cpp ~4MB trên Windows). macOS: STT offline cần <code>brew install whisper-cpp</code>.</li>
<li>Vẫn có thể dùng <strong>máy chủ</strong> (OpenAI-compatible): Edge-TTS, Kokoro, Faster-Whisper, OpenAI, Groq…</li>
<li><strong>🎤 Nói thay vì gõ:</strong> sau khi bật Nhận giọng nói, ô chat (Quick Chat &amp; bong bóng) có nút 🎤 → bấm, nói, bấm ⏹ → chữ hiện trong ô nhập để bạn xem lại rồi bấm Gửi (tối đa 60 giây mỗi lần).</li>
<li><strong>🔊 / 🔇</strong> trên đầu bong bóng chat: bật/tắt Ted đọc câu trả lời (chỉ hiện khi đã cấu hình giọng nói).</li>
</ul>
<h3><a name="sec33"></a>9.3. 📐 Công thức toán, bảng, hình vẽ trong chat &amp; ôn tập</h3>
<ul>
<li>Ted hiển thị <strong>công thức LaTeX</strong> (<code>$x^2$</code>, <code>$$\dfrac{a}{b}$$</code>, hệ phương trình <code>cases</code>, ma trận), <strong>bảng / biểu mẫu</strong> markdown, ô tích ☐/☑ và <strong>hình vẽ SVG</strong> (tam giác, trục số, đồ thị) trên nền trắng dễ nhìn.</li>
<li>Áp dụng cho Quick Chat, bong bóng chat, câu hỏi trắc nghiệm, gợi ý, lời giải. Khi đọc TTS, công thức được đọc thành lời (“x bình phương cộng 1 phần 2”).</li>
</ul>
<hr />
<h2><a name="sec35"></a>10. Hub, Họp, Gỡ Rối &amp; Phím Tắt Toàn Cục</h2>
<h3><a name="sec36"></a>10.1. 🏆 Hub của Ted (Gamification)</h3>
<ul>
<li><strong>Thanh tiến độ tuần 0–100%:</strong> mỗi thứ Hai bắt đầu lại ở <strong>50% (Cấp 5)</strong>. <strong>Cấp</strong> = ⌈% / 10⌉ (từ 1 đến 10). Việc học/làm (Pomodoro, task xong, bài tập) cộng %; ngày chưa đủ 20 XP bị trừ 5%; bỏ đánh dấu task đã xong thì trừ lại.</li>
<li><strong>6 chỉ số</strong> (⚡ Năng lượng, 📚 Dữ liệu, 🎓 Học tập, 🖥 Tải màn hình, 🎈 Gắn kết / Quan hệ, 💚 Sức khỏe): tính <strong>luỹ kế trong tuần</strong>, cũng bắt đầu từ 50 mỗi thứ Hai. Rê chuột vào từng chỉ số để xem cách tính.</li>
<li><strong>53 huy hiệu:</strong> mở khi đạt điều kiện; đã mở là <strong>vĩnh viễn</strong>, reset tuần không khoá lại. Hub luôn hiển thị các huy hiệu từng mở.</li>
<li><strong>Nhật ký tuần (Weekly log):</strong> lưu % cuối tuần, cấp đỉnh, chỉ số và huy hiệu của từng tuần.</li>
<li><strong>Nút 🎒 Đi chơi / gia đình / du lịch:</strong> ghi thủ công một lần đi chơi (chọn ngày: hôm nay hoặc vài ngày trước, có giới hạn mỗi ngày). Nghỉ ngơi không tạo XP nhưng tăng chỉ số <strong>Sức khỏe</strong> và <strong>Gắn kết</strong>.</li>
<li><strong>Cách mở:</strong> Dashboard → <strong>🏆 Hub của Ted</strong>, menu chuột phải / khay hệ thống, hoặc <code>Ctrl+Alt+G</code>. Chip cấp độ hiện cạnh nhân vật.</li>
<li><strong>Riêng tư:</strong> Ted không theo dõi bàn phím, chuột hay màn hình. Số liệu lấy từ thời điểm Ted chạy/tắt, phiên tập trung, task và bài tập đã có.</li>
</ul>
<h3><a name="sec37"></a>10.2. 🎭 Thư viện nhân vật (Character Gallery) &amp; mở khoá</h3>
<ul>
<li>Vào Dashboard → <strong>🎭 Nhân vật</strong> (cũng mở được từ menu chuột phải, khay hệ thống hoặc Cài đặt). Mọi thao tác đổi nhân vật đều đi qua thư viện này.</li>
<li>6 con vật mặc định <strong>luôn miễn phí</strong>. Ngoài ra có <strong>36 nhân vật</strong> thuộc 6 pack, mỗi nhân vật có <strong>điều kiện mở khoá riêng</strong>: số huy hiệu đã mở, một huy hiệu cụ thể, hoặc chỉ số trọn đời (số phiên Deep Work, phút tập trung, task xong, câu trắc nghiệm, phiên Gỡ Rối, cấp cao nhất đạt được, chuỗi ngày, số lần đi chơi, tổng XP...).</li>
<li>Nhân vật bị khoá hiện kèm điều kiện còn thiếu. Điều kiện được kiểm tra mỗi lần Hub làm mới; nhân vật mới mở sẽ có thông báo. Đã mở là <strong>vĩnh viễn</strong> (cấp tuần xuống không khoá lại).</li>
</ul>
<h3><a name="sec38"></a>10.3. 👥 Chế độ Họp / Học nhóm</h3>
<ul>
<li>Dùng <strong>thay cho Deep Work</strong> khi họp team, học nhóm hoặc học với thầy cô.</li>
<li><strong>Bắt đầu:</strong> menu chuột phải → <strong>👥 Bắt đầu Họp / Học nhóm</strong>, khay hệ thống, Dashboard, hoặc <code>Ctrl+Alt+M</code> (bấm lần nữa để kết thúc). Hộp nhập chủ đề là <strong>tuỳ chọn</strong> (loại: Họp team / Học nhóm / Học với thầy cô / Khác); bấm <strong>Bỏ qua, bắt đầu luôn</strong> nếu không cần.</li>
<li>Đồng hồ <strong>đếm lên</strong> (không đếm ngược). Nhắc chánh niệm và gợi ý Gỡ Rối bị tạm dừng trong lúc họp.</li>
<li>XP 1 / 10 phút (tối đa 12 XP/ngày), tăng mạnh chỉ số <strong>Gắn kết / Quan hệ</strong>, có 3 huy hiệu riêng. Não AI chỉ nhận số liệu (số phiên, số phút), <strong>không nhận chủ đề</strong>.</li>
</ul>
<h3><a name="sec39"></a>10.4. 🎒 Nhắc nghỉ nhỏ sau Deep Work &amp; Họp (Health micro-break)</h3>
<ul>
<li>Sau mỗi phiên Deep Work hoặc Họp hoàn tất, Ted gợi ý <strong>một việc nghỉ ngắn</strong> (uống nước, đứng dậy vươn vai, nhìn xa 20-20-20, hít thở...). Gợi ý cũng hiện trong quãng nghỉ tự động ngay sau phiên Deep Work.</li>
<li>Không bao giờ hiện giữa lúc đang Deep Work hoặc đang họp, và chỉ hiện <strong>một lần</strong> cho mỗi phiên hoàn tất. Có thể tắt trong Cài đặt.</li>
<li>Bấm <code>✅ Đã làm</code> để ghi nhận (cộng chỉ số <strong>Sức khỏe</strong> có trần mỗi ngày, <strong>không</strong> cộng XP) hoặc <code>⏭ Bỏ qua</code>. Gợi ý do Não AI (skill <code>ted-health-break</code>) đưa ra; khi Không khả dụng, Ted dùng gợi ý offline.</li>
</ul>
<h3><a name="sec40"></a>10.5. 🧶 Gỡ rối ý tưởng (Idea Untangling)</h3>
<ul>
<li>Hội thoại giúp tháo một ý tưởng rối thành các bước rõ ràng. Mở bằng <code>Ctrl+Alt+Space</code>, menu chuột phải hoặc bong bóng gợi ý.</li>
<li><strong>Tóm tắt &amp; Phản biện (Summarize &amp; Critique):</strong> Não AI trả về tóm tắt, sơ đồ luồng làm nổi bật bước còn thiếu, các khoảng trống và bước tiếp theo.</li>
<li><strong>Ghi chú:</strong> bấm <strong>Lưu vào ghi chú task</strong> (nối vào ghi chú của task) hoặc <strong>➕ Tạo task bước tiếp</strong>.</li>
<li>Gợi ý tự động: tối đa 2 lần/ngày, cách nhau ít nhất 90 phút, tối đa 1 lần/task/ngày; có thể tắt bằng một công tắc.</li>
</ul>
<h3><a name="sec41"></a>10.6. ⌨️ Phím tắt toàn cục (Global hotkeys)</h3>
<p>Chỉnh tại Dashboard → Cài đặt → <strong>⌨️ Phím tắt</strong>: bấm vào ô rồi nhấn tổ hợp mới (cần Ctrl / Alt / ⌘ / ⌃), bật/tắt từng phím, <strong>↺ Khôi phục tất cả</strong>.</p>
<table width="100%" cellspacing="0" cellpadding="8">
<thead>
<tr>
<th>Hành động</th>
<th>Windows / Linux</th>
<th>macOS</th>
</tr>
</thead>
<tbody>
<tr>
<td>🧩 Gỡ rối ý tưởng</td>
<td><code>Ctrl+Alt+Space</code></td>
<td><code>⌘⌥⌃Space</code></td>
</tr>
<tr>
<td>⏸ Bắt đầu / Tạm dừng Pomodoro</td>
<td><code>Ctrl+Alt+P</code></td>
<td><code>⌃⌥P</code></td>
</tr>
<tr>
<td>⏹ Dừng phiên tập trung</td>
<td><code>Ctrl+Alt+X</code></td>
<td><code>⌃⌥X</code></td>
</tr>
<tr>
<td>☕ Chuyển sang nghỉ ngắn</td>
<td><code>Ctrl+Alt+B</code></td>
<td><code>⌃⌥B</code></td>
</tr>
<tr>
<td>📋 Mở Trung tâm quản lý</td>
<td><code>Ctrl+Alt+D</code></td>
<td><code>⌃⌥D</code></td>
</tr>
<tr>
<td>💬 Mở chat nhanh với Ted</td>
<td><code>Ctrl+Alt+C</code></td>
<td><code>⌃⌥C</code></td>
</tr>
<tr>
<td>🅿️ Cất nhanh ý tưởng vào Bãi đỗ</td>
<td><code>Ctrl+Alt+N</code></td>
<td><code>⌃⌥N</code></td>
</tr>
<tr>
<td>🐾 Hiện / Ẩn Ted</td>
<td><code>Ctrl+Alt+H</code></td>
<td><code>⌃⌥H</code></td>
</tr>
<tr>
<td>🏆 Mở Hub Đồng hành</td>
<td><code>Ctrl+Alt+G</code></td>
<td><code>⌃⌥G</code></td>
</tr>
<tr>
<td>👥 Bắt đầu / Kết thúc Họp / Học nhóm</td>
<td><code>Ctrl+Alt+M</code></td>
<td><code>⌃⌥M</code></td>
</tr>
</tbody>
</table>
<p>Tổ hợp trùng hành động khác của Ted hoặc đã bị ứng dụng/hệ thống chiếm sẽ bị từ chối và giữ phím cũ. Nếu không đăng ký được phím toàn cục, phím chỉ hoạt động khi Ted đang mở.</p>
<h3><a name="sec42"></a>10.7. 🧠 Báo cáo tăng trưởng gửi Não AI (Growth reports)</h3>
<ul>
<li>Ted gửi cho Não AI báo cáo ngày/tuần (skill <code>ted-growth-hub</code>) gồm %, cấp, 6 chỉ số và huy hiệu để Não AI có thể động viên, tư vấn và lưu nhật ký tăng trưởng.</li>
<li><strong>Quyền riêng tư:</strong> báo cáo <strong>chỉ chứa số liệu tổng hợp (counts)</strong> như số phiên, số phút, số lần nghỉ. Không gửi nội dung công việc, chủ đề họp, ghi chú, nội dung gỡ rối hay bất kỳ dữ liệu từ bàn phím, chuột, màn hình.</li>
<li>Khi mất mạng, báo cáo xếp hàng chờ và tự gửi lại khi kết nối trở lại.</li>
</ul>
<hr />
<h2><a name="sec34"></a>11. Bảng Tra Cứu Thuật Ngữ A–Z (Glossary)</h2>
<table width="100%" cellspacing="0" cellpadding="8">
<thead>
<tr>
<th>Thuật ngữ</th>
<th>Tiếng Anh / Viết tắt</th>
<th>Giải thích ngắn gọn</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Ambient Audio</strong></td>
<td>Âm thanh môi trường</td>
<td>Tiếng mưa rơi hoặc âm thanh trắng giúp cách ly tạp âm bên ngoài, hỗ trợ tập trung.</td>
</tr>
<tr>
<td><strong>Brain Dump</strong></td>
<td>Trút bỏ tư duy</td>
<td>Thao tác ghi nhanh tất cả các suy nghĩ rối rắm ra giấy hoặc bãi đỗ để làm trống bộ nhớ não bộ.</td>
</tr>
<tr>
<td><strong>Context Menu</strong></td>
<td>Menu ngữ cảnh</td>
<td>Bảng tùy chọn bật ra khi bạn nhấp chuột phải vào nhân vật Ted hoặc khay hệ thống.</td>
</tr>
<tr>
<td><strong>Daily Journal</strong></td>
<td>Nhật ký ngày</td>
<td>Mục ghi lại tiến độ, cảm xúc và bài học phản tư vào cuối mỗi ngày làm việc.</td>
</tr>
<tr>
<td><strong>Deep Work</strong></td>
<td>Làm việc sâu</td>
<td>Trạng thái làm việc tập trung cao độ, không bị xao nhãng, mang lại hiệu suất tối đa.</td>
</tr>
<tr>
<td><strong>FastMCP</strong></td>
<td>Model Context Protocol</td>
<td>Giao thức mở cho phép não bộ AI kết nối và tương tác với các công cụ trên máy tính.</td>
</tr>
<tr>
<td><strong>Focus Session</strong></td>
<td>Phiên tập trung</td>
<td>Khoảng thời gian 25 phút đếm ngược chuyên tâm cho duy nhất một nhiệm vụ.</td>
</tr>
<tr>
<td><strong>Não AI (Cloud / VPS)</strong></td>
<td>Não bộ AI (Cloud / VPS)</td>
<td>Trí tuệ nhân tạo điều phối thông minh. Hỗ trợ chạy trên Cloud VPS (24/7) hoặc Local, lưu trữ tri thức và ký ức dài hạn mà không bắt buộc lưu trữ cục bộ.</td>
</tr>
<tr>
<td><strong>Intent Locking</strong></td>
<td>Khóa chủ đích</td>
<td>Thao tác cam kết hoàn thành duy nhất 1 mục tiêu cụ thể trước khi bấm bắt đầu Pomodoro.</td>
</tr>
<tr>
<td><strong>Leitner Box</strong></td>
<td>Hộp Leitner</td>
<td>Phương pháp chia các ngăn thẻ học theo mức độ thành thạo để lên lịch lặp lại ngắt quãng.</td>
</tr>
<tr>
<td><strong>Local-First &amp; Hybrid</strong></td>
<td>Lưu trữ kết hợp</td>
<td>Cơ chế kết hợp bộ đệm siêu tốc trên máy tính cá nhân với bộ nhớ trí tuệ lâu dài trên VPS/Cloud, đảm bảo vừa phản hồi tức thì vừa lưu trữ đám mây bền vững.</td>
</tr>
<tr>
<td><strong>Mindful Ping</strong></td>
<td>Chuông chánh niệm</td>
<td>Nhịp chuông định kỳ sau mỗi 15-20 phút giúp bạn tự nhận thức xem mình có đang xao nhãng không.</td>
</tr>
<tr>
<td><strong>Parking Lot</strong></td>
<td>Bãi đỗ xao nhãng</td>
<td>Nơi cất tạm các ý tưởng hoặc việc đột xuất nảy sinh trong lúc làm việc để giải quyết sau.</td>
</tr>
<tr>
<td><strong>Pomodoro</strong></td>
<td>Quả cà chua</td>
<td>Kỹ thuật chia thời gian làm việc thành các chu kỳ 25 phút tập trung xen kẽ 5 phút nghỉ ngơi.</td>
</tr>
<tr>
<td><strong>Proactive Nudge</strong></td>
<td>Lời nhắc chủ động</td>
<td>Tin nhắn nhắc nhở mà AI chủ động gửi tới bạn khi phát hiện sự kiện hoặc lịch họp quan trọng.</td>
</tr>
<tr>
<td><strong>Rocks</strong></td>
<td>Tảng đá lớn</td>
<td>3–5 mục tiêu chiến lược quan trọng nhất cần được hoàn thành trước các việc vụn vặt.</td>
</tr>
<tr>
<td><strong>Skin / Chibi</strong></td>
<td>Nhân vật diện mạo</td>
<td>Hình ảnh hoạt họa đại diện cho Ted (Mèo, Cú, Gấu trúc, Shiba, Thỏ bông, Cánh cụt).</td>
</tr>
<tr>
<td><strong>Spaced Repetition (SRS)</strong></td>
<td>Lặp lại ngắt quãng</td>
<td>Phương pháp khoa học ôn tập kiến thức tăng dần theo khoảng thời gian để ghi nhớ vĩnh viễn.</td>
</tr>
<tr>
<td><strong>System Tray</strong></td>
<td>Khay hệ thống</td>
<td>Khu vực góc dưới bên phải màn hình Windows (hoặc thanh trạng thái trên cùng macOS).</td>
</tr>
</tbody>
</table>
"""
