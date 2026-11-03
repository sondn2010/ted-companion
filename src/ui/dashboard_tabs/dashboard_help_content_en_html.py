"""Nội dung cẩm nang Trợ giúp (English) dạng HTML — CSS áp từ dashboard_help_tab_widget.py."""

HELP_HTML_EN = r"""
<h1>🐾 Ted Companion — Handbook &amp; Terminology Guide</h1>
<p>Welcome to <strong>Ted Companion</strong> — your friendly desktop companion designed to help you maintain a state of <strong>Deep Work</strong>, conquer distractions, and seamlessly interface with the <strong>AI Brain</strong> AI brain.</p>
<p>This guide explains all concepts, features, and terminology across the application.</p>
<hr />
<h2><a name="sec1"></a>📑 Table of Contents</h2>
<ol>
<li><a href="#sec2">Core Philosophy &amp; Architecture</a></li>
<li><a href="#sec5">Companions (Chibi Skins) &amp; Ambient Sound</a></li>
<li><a href="#sec9">Deep Work Timer &amp; Pomodoro Cycle</a></li>
<li><a href="#sec14">Mindful Pings &amp; Proactive Nudges</a></li>
<li><a href="#sec17">Distraction Parking Lot &amp; Brain Dump</a></li>
<li><a href="#sec21">AI Brain (Cloud / VPS) (Artificial Intelligence)</a></li>
<li><a href="#sec26">Specialized Modular Architecture</a>
<ul>
<li><a href="#sec27">Work Assistant Module</a></li>
<li><a href="#sec28">Learning Coach &amp; SRS Module</a></li>
</ul>
</li>
<li><a href="#sec29">Dashboard &amp; Flexible Storage (Hybrid: Local Cache + Cloud/VPS Brain)</a></li>
<li><a href="#sec30">Mouse Gestures, Speech Bubble &amp; Shortcuts</a></li>
<li><a href="#sec35">Hub, Meetings, Untangling &amp; Global Hotkeys</a></li>
<li><a href="#sec34">Glossary of Terms (A–Z)</a></li>
</ol>
<hr />
<h2><a name="sec2"></a>1. Core Philosophy &amp; Architecture</h2>
<h3><a name="sec3"></a>1.1. Design Philosophy</h3>
<ul>
<li><strong>Non-intrusive:</strong> Ted respects your privacy. It does not take covert screenshots or record open windows. Ted accompanies you through mindfulness and respectful, periodic check-ins.</li>
<li><strong>Cozy &amp; Non-judgmental:</strong> When distractions happen, Ted never penalizes or scolds you. Instead, it gently helps you register the thought and return to your productive flow.</li>
<li><strong>Hybrid Architecture (Local-First Client Cache + Cloud/VPS Brain):</strong>
<ul>
<li><strong>Local-First Cache:</strong> Everyday task workflows, dashboard views, and countdown timers are cached locally in SQLite on your workstation, guaranteeing zero-latency interactions and flawless offline capability.</li>
<li><strong>Cloud / VPS Brain Support:</strong> The AI intelligence layer (AI Brain) <strong>is not restricted to local storage</strong>. You can run and host the Brain on a 24/7 cloud server or private VPS. All long-term memories (<code>memories/</code>), knowledge bases (<code>knowledge/</code>), user profiles, and learning progress persist safely in the cloud, syncing effortlessly across multiple devices without consuming local machine resources.</li>
</ul>
</li>
</ul>
<h3><a name="sec4"></a>1.2. Two-Tier Architecture</h3>
<ul>
<li><strong>GUI Layer (Ted Desktop Client - PySide6):</strong> The &quot;body&quot; of the companion. A lightweight, frameless, translucent widget floating on your desktop that runs zero-latency countdown timers, plays ambient audio, and hosts the control Dashboard.</li>
<li><strong>Intelligence Layer (AI Brain (Cloud / VPS)):</strong> The &quot;mind&quot; of the companion running flexibly on a private VPS / Cloud (24/7) or locally. AI Brain breaks down complex goals, stores long-term memory, and analyzes queries via network APIs.</li>
</ul>
<hr />
<h2><a name="sec5"></a>2. Companions (Chibi Skins) &amp; Ambient Sound</h2>
<h3><a name="sec6"></a>2.1. Six Chibi Characters</h3>
<p>Ted Companion offers 6 handcrafted SVG vector characters that smoothly animate based on your focus state:</p>
<ol>
<li><strong>🐱 Ted the Cat (<code>cat</code>):</strong> Playful, warm, diligently typing alongside you.</li>
<li><strong>🐕 Shiba Pup (<code>shiba</code>):</strong> Loyal, energetic, and always cheering you on.</li>
<li><strong>🐰 Bunny (<code>bunny</code>):</strong> Gentle and quiet, promoting calm and tranquility.</li>
<li><strong>🐧 Penguin (<code>penguin</code>):</strong> Neat and disciplined, a symbol of steady perseverance.</li>
<li><strong>🦉 Night Owl (<code>owl</code>):</strong> Wise and observant, ideal for late-night focus sessions.</li>
<li><strong>🐼 Panda (<code>panda</code>):</strong> Calm and balanced, helping ease workplace anxiety.</li>
</ol>
<h3><a name="sec7"></a>2.2. Animation States</h3>
<ul>
<li><code>IDLE</code>: Resting, occasionally blinking or reading a book while waiting for you to begin.</li>
<li><code>FOCUSING</code>: Wearing headphones, typing on a keyboard, or deeply absorbed in work during a Deep Work session.</li>
<li><code>NUDGING</code>: Holding up a discreet sign or gently waving to check in on you.</li>
<li><code>CELEBRATING</code>: Waving a flag or cheering when you successfully complete a session.</li>
<li><code>SLEEPING</code>: Curled up asleep during scheduled downtime or long breaks.</li>
</ul>
<h3><a name="sec8"></a>2.3. Ambient Sound</h3>
<ul>
<li><strong>Continuous Rainfall Audio:</strong> Looping ambient rain sounds that mask background noise (white noise), guiding your brain waves toward the focused Alpha state.</li>
<li><strong>Mindful Chimes:</strong> Soft wind chimes marking interval check-ins or session transitions without jarring your concentration.</li>
</ul>
<hr />
<h2><a name="sec9"></a>3. Deep Work Timer &amp; Pomodoro Cycle</h2>
<h3><a name="sec10"></a>3.1. What is Deep Work?</h3>
<p>A term coined by Cal Newport describing distraction-free, high-concentration cognitive work that pushes your mental faculties to their limit, generating high-value output in minimal time.</p>
<h3><a name="sec11"></a>3.2. The Pomodoro Technique</h3>
<p>A time management framework that breaks work into manageable intervals:</p>
<ul>
<li><strong>Focus Session:</strong> Defaults to 25 minutes (configurable from 15 to 60 minutes in Settings).</li>
<li><strong>Short Break:</strong> Defaults to 5 minutes to stand up, hydrate, and relax your eyes.</li>
<li><strong>Long Break:</strong> A 15–30 minute rest taken after completing 4 consecutive Pomodoro cycles.</li>
</ul>
<h3><a name="sec12"></a>3.3. Intent Locking</h3>
<p>When starting a session, Ted prompts you with a single question: <em>&quot;During the next 25 minutes, what is the single, tangible outcome you will achieve?&quot;</em> Committing to one concrete result prevents multitasking.</p>
<h3><a name="sec13"></a>3.4. Session Review &amp; Rating</h3>
<p>When time expires, Ted celebrates your effort and lets you rate your focus level (1–5 stars) along with optional notes. These metrics are aggregated in the Analytics dashboard to track your long-term focus habits.</p>
<hr />
<h2><a name="sec14"></a>4. Mindful Pings &amp; Proactive Nudges</h2>
<h3><a name="sec15"></a>4.1. Mindful Ping Loop</h3>
<ul>
<li>Every 15 or 20 minutes during a focus session, Ted plays a gentle chime and displays a subtle banner: <em>&quot;Are you still working on [Task Name]?&quot;</em>.</li>
<li><strong>One-Tap Responses:</strong>
<ul>
<li>Click <code>[👍 Still Focused]</code>: Ted retreats to the corner (or auto-dismisses after 8 seconds if you are actively typing).</li>
<li>Click <code>[😅 Got Distracted]</code>: Ted logs the distraction count without judgment and encourages a deep breath before resuming.</li>
</ul>
</li>
</ul>
<h3><a name="sec16"></a>4.2. Proactive Nudges</h3>
<p>When connected to the AI Brain, Ted can proactively deliver contextual alerts (e.g., <em>&quot;Upcoming team standup in 10 minutes&quot;</em> or <em>&quot;You have 2 strategic Rocks scheduled for review today&quot;</em>).</p>
<hr />
<h2><a name="sec17"></a>5. Distraction Parking Lot &amp; Brain Dump</h2>
<h3><a name="sec18"></a>5.1. The &quot;Sudden Idea Bubble&quot; Problem</h3>
<p>In the middle of focused coding or writing, a stray thought strikes: <em>&quot;I must reply to that client email&quot;</em>, or <em>&quot;Let me research library X&quot;</em>. Switching tabs immediately causes you to lose focus, requiring 15–20 minutes to regain your flow state.</p>
<h3><a name="sec19"></a>5.2. Distraction Parking Lot Solution</h3>
<p>The Parking Lot is a safe holding area for stray thoughts:</p>
<ol>
<li>Click Ted to open the small chat bubble (or double-click / use the hotkey to open the 💬 Chat page in the app).</li>
<li>Type your thought and press <strong><code>🅿️ Parking Lot</code> (Ctrl + Enter)</strong>.</li>
<li>The thought is instantly parked into your local database. You can return to your task with peace of mind.</li>
</ol>
<h3><a name="sec20"></a>5.3. Brain Dump &amp; Quick Chat</h3>
<ul>
<li>Type your question and press <strong><code>💬 Chat</code> (Enter)</strong>: Streams an inquiry directly to the AI Brain AI brain, with responses displayed right inside the speech bubble.</li>
<li>Press <strong><code>Esc</code></strong>: Instantly dismisses the speech bubble.</li>
</ul>
<hr />
<h2><a name="sec21"></a>6. AI Brain (Cloud / VPS) (Artificial Intelligence)</h2>
<h3><a name="sec22"></a>6.1. What is AI Brain?</h3>
<p><strong>AI Brain</strong> is an autonomous agent engine capable of long-term memory, planning, and tool execution over network APIs.</p>
<h3><a name="sec23"></a>6.2. Operating the Brain on VPS / Cloud or Locally (No Local-Only Restriction)</h3>
<p>Ted offers complete hosting and storage flexibility for the AI Brain:</p>
<ul>
<li><strong>VPS / Cloud Mode (24/7 - Recommended):</strong>
<ul>
<li><strong>Persistent Cloud Storage:</strong> Long-term memories (<code>memories/MEMORY.md</code>, <code>USER.md</code>), knowledge documents (<code>knowledge/</code>), persona definitions (<code>SOUL.md</code>), and custom domain skills (<code>skills/</code>) are hosted directly on your private cloud VPS.</li>
<li><strong>Decoupled from Local Machines:</strong> You are <strong>not required to store data only on your local workstation</strong>. Even when your laptop is turned off or you travel, the Brain continues operating on the cloud, retaining context and ready to sync with any client device.</li>
<li><strong>Multi-Device &amp; Family Friendly:</strong> A single VPS instance can manage independent profiles (<code>family_work</code>, <code>family_thcs</code>, <code>family_duhoc</code>, <code>family_caohoc</code>), serving parents and children without data fragmentation or storage penalties on client machines.</li>
<li><strong>Proactive 24/7 Automation:</strong> The cloud Brain actively monitors calendar events, prepares upcoming agendas, and delivers mindful reminders automatically.</li>
</ul>
</li>
<li><strong>Local Mode:</strong> For users who prefer a 100% offline, isolated environment running entirely on their single workstation at <code>http://localhost:8000</code>.</li>
</ul>
<h3><a name="sec24"></a>6.3. FastMCP Server (Model Context Protocol)</h3>
<p>Ted Companion embeds a FastMCP Server, allowing the AI Brain brain to call back into Ted and execute native functions:</p>
<ul>
<li>Start or stop Pomodoro sessions.</li>
<li>Add new tasks to your backlog.</li>
<li>Append reflections to your Daily Journal.</li>
<li>Switch Ted's animation and mood.</li>
</ul>
<h3><a name="sec25"></a>6.4. Multi-Profile Support</h3>
<p>Connect multiple independent profiles suited for different roles and family members:</p>
<ul>
<li><code>family_work</code>: Professional work assistant for parents and knowledge workers.</li>
<li><code>thcs</code>: Middle-school curriculum tutor (Math, Literature, English).</li>
<li><code>duhoc</code>: Overseas study advisory profile for test prep and application roadmaps.</li>
<li><code>caohoc</code>: Graduate school and academic research assistant.</li>
</ul>
<hr />
<h2><a name="sec26"></a>7. Specialized Modular Architecture</h2>
<p>Ted features an extensible plug-and-play module system. Modules can be toggled on or off in the Settings tab:</p>
<h3><a name="sec27"></a>7.1. Work Assistant Module (<code>work</code>)</h3>
<p>Tailored for knowledge workers and project managers:</p>
<ul>
<li><strong>Strategic Rocks:</strong> Inspired by OKRs and Stephen Covey's Big Rocks metaphor. Every quarter or month, commit to 3–5 high-impact strategic priorities. Ted ensures these Rocks take precedence over small gravel tasks.</li>
<li><strong>Morning Briefing:</strong> A quick start overview summarizing today's meetings, deadlines, and core priorities.</li>
<li><strong>Calendar Cache &amp; Meeting Alerts:</strong> Syncs with Google Calendar or Outlook to give you timely 5–10 minute heads-up notifications without interrupting your thought process.</li>
</ul>
<h3><a name="sec28"></a>7.2. Learning Coach &amp; SRS Module (<code>coach</code>)</h3>
<p>Tailored for students and lifelong learners:</p>
<ul>
<li><strong>Spaced Repetition System (SRS):</strong> A proven memory technique that schedules reviews just as knowledge is about to fade, cementing facts into long-term memory.</li>
<li><strong>5 Leitner Boxes:</strong>
<ul>
<li><strong>Box 1:</strong> New or forgotten cards — Reviewed daily.</li>
<li><strong>Box 2:</strong> Answered correctly once — Reviewed every 2 days.</li>
<li><strong>Box 3:</strong> Answered correctly twice — Reviewed every 4 days.</li>
<li><strong>Box 4:</strong> Answered correctly three times — Reviewed every 7 days.</li>
<li><strong>Box 5:</strong> Mastered — Reviewed every 14–30 days.</li>
<li><em>Golden Rule:</em> Correct answers promote the card to the next box; incorrect answers demote the card back to Box 1 for reinforcement.</li>
</ul>
</li>
<li><strong>Rich Exercise Formats:</strong>
<ul>
<li><code>Quiz</code>: 4-option multiple choice questions with detailed explanations.</li>
<li><code>Flashcard</code>: Two-sided terminology cards.</li>
<li><code>Step-by-step</code>: Guided multi-step problem solving.</li>
<li><code>Writing</code>: Essay practice with AI critique and feedback.</li>
</ul>
</li>
<li><strong>Milestones &amp; Progress Reports:</strong> Track learned card counts, mastery curves, and export progress summaries for parents and educators.</li>
</ul>
<hr />
<h2><a name="sec29"></a>8. Dashboard &amp; Flexible Storage (Hybrid: Local Cache + Cloud/VPS Brain)</h2>
<p>Ted utilizes a hybrid storage architecture:</p>
<ul>
<li><strong>Local Workstation Cache:</strong> Powers instant dashboard loading, snappy task management, and offline focus tracking with SQLite.</li>
<li><strong>Cloud / VPS Brain:</strong> Handles deep knowledge retrieval, long-term memory accumulation, and cross-device continuity. You are never confined to local-only storage.</li>
</ul>
<p>Right-click Ted and select <strong>📋 Management Center</strong> to open the main Dashboard:</p>
<ul>
<li><strong>Tasks &amp; Parking Lot Tab:</strong> Manage your workflow (<code>Todo</code>, <code>Doing</code>, <code>Done</code>) and promote parked ideas into actionable tasks.</li>
<li><strong>Daily Journal Tab:</strong> An end-of-day reflection space to log accomplishments, key learnings, and personal insights.</li>
<li><strong>Focus Analytics Tab:</strong> Visual metrics displaying your total deep work hours, completed sessions, and mindfulness ratings across days and weeks.</li>
<li><strong>Help Tab:</strong> Where you are reading this document! Content follows the selected app language (Vietnamese / English) and supports fast keyword search.</li>
<li><strong>Settings Tab:</strong> Configure Pomodoro lengths, select companion characters, manage AI Brain connections (Local or Cloud VPS), and toggle modules.</li>
</ul>
<hr />
<h2><a name="sec30"></a>9. Mouse Gestures, Speech Bubble &amp; Shortcuts</h2>
<table width="100%" cellspacing="0" cellpadding="8">
<thead>
<tr>
<th>Action</th>
<th>Location</th>
<th>Behavior</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Left Click</strong></td>
<td>Ted Character Body</td>
<td>Opens the small chat &amp; Parking Lot bubble; the first line is a cheer plus your current / urgent tasks.</td>
</tr>
<tr>
<td><strong>Double Click</strong></td>
<td>Ted Character Body</td>
<td>Opens the large <strong>💬 Chat</strong> page in the app (easier to read).</td>
</tr>
<tr>
<td><strong>Left Click + Drag</strong></td>
<td>Ted Character Body</td>
<td>Moves the companion widget anywhere on your screen.</td>
</tr>
<tr>
<td><strong>Right Click</strong></td>
<td>Ted Character Body</td>
<td>Opens the Context Menu (Pomodoro controls, skins, ambient audio, dashboard, settings, help).</td>
</tr>
<tr>
<td><strong>Left / Right Click</strong></td>
<td>System Tray Icon</td>
<td>Toggles Ted visibility, opens Dashboard, triggers Pomodoro, or quits.</td>
</tr>
<tr>
<td><strong>Enter Key</strong></td>
<td>Speech Bubble Input</td>
<td>Sends message to AI Brain (<code>💬 Chat</code>).</td>
</tr>
<tr>
<td><strong>Ctrl + Enter Key</strong></td>
<td>Speech Bubble Input</td>
<td>Parks the idea into the Distraction Parking Lot (<code>🅿️ Parking Lot</code>).</td>
</tr>
<tr>
<td><strong>Esc Key</strong></td>
<td>Speech Bubble Input</td>
<td>Dismisses the speech bubble immediately.</td>
</tr>
<tr>
<td><strong>🤫 5 quick clicks</strong></td>
<td>Character Body</td>
<td><strong>Hidden action:</strong> opens <strong>🎭 Character Persona</strong> (own name, personality, own voice).</td>
</tr>
</tbody>
</table>
<h3><a name="sec31"></a>9.1. 🤫 Hidden Actions (easy to forget — listed here)</h3>
<table width="100%" cellspacing="0" cellpadding="8">
<thead>
<tr>
<th>Hidden action</th>
<th>How</th>
<th>Notes</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>🎭 Character Persona</strong></td>
<td>Click the character <strong>5 times quickly</strong></td>
<td>Each character (Cat, Owl, Panda, Shiba, Bunny, Penguin) gets its <strong>own name</strong>, <strong>personality</strong> (Cheerful, Calm, Energetic, Sweet, Funny, Disciplined) and <strong>own TTS voice</strong> (server voice / offline voice / speed). Press <strong>🔊 Test</strong>, then <strong>💾 Save</strong>. <strong>↺ Reset</strong> removes it.</td>
</tr>
<tr>
<td>Double click</td>
<td>Click twice</td>
<td>Because of the 5-click gesture, chat opens after a short beat (~0.5s) so the app knows whether you keep clicking.</td>
</tr>
</tbody>
</table>
<blockquote>
<p>Personas are <strong>app-side settings only</strong>: display name, single-click catchphrases and TTS voice. <strong>System prompts are not changed</strong> — the conversation is still driven by the AI Brain.</p>
</blockquote>
<h3><a name="sec32"></a>9.2. 🔊 Text-to-Speech &amp; 🎙️ Speech Recognition — download models inside the app</h3>
<ul>
<li>The installer ships <strong>without voice models</strong>. Go to <strong>Dashboard → ⚙️ Settings → Voice / Speech Recognition</strong>:
<ol>
<li>Press <strong>✨ Choose a preset…</strong> → a <strong>searchable</strong> popup (accents optional: <code>cham</code>, <code>offline</code>, <code>english</code>, <code>openai</code>…) with 20+ presets → <strong>Fill in settings</strong>.</li>
<li>Offline preset without the model → the app offers to <strong>download now</strong>. Or press <strong>⬇️ Download / manage offline voices…</strong> (size, quality, ⭐ recommended).</li>
<li>After download the app <strong>switches to “This computer (offline)”</strong> and pre-selects the model → <strong>Test</strong> → <strong>💾 Save voice settings</strong>.</li>
</ol>
</li>
<li>Models live in <code>~/.ted/voice_models/</code> and can be deleted from the download popup. The first download also fetches a small runtime (Piper ~22MB, whisper.cpp ~4MB on Windows). macOS offline STT needs <code>brew install whisper-cpp</code>.</li>
<li>Servers (OpenAI-compatible) still work: Edge-TTS, Kokoro, Faster-Whisper, OpenAI, Groq…</li>
<li><strong>🎤 Speak instead of typing:</strong> once Speech Recognition is enabled, chat inputs (Quick Chat &amp; bubble) show a 🎤 button → click, speak, click ⏹ → the text appears in the input for review before Send (max 60s per take).</li>
<li><strong>🔊 / 🔇</strong> on the chat bubble header toggles Ted reading replies aloud (shown only when TTS is configured).</li>
</ul>
<h3><a name="sec33"></a>9.3. 📐 Math, Tables &amp; Figures in Chat and Review</h3>
<ul>
<li>Ted renders <strong>LaTeX math</strong> (<code>$x^2$</code>, <code>$$\dfrac{a}{b}$$</code>, <code>cases</code> systems, matrices), markdown <strong>tables / forms</strong>, ☐/☑ checklists and <strong>SVG figures</strong> (triangles, number lines, graphs) on a white board.</li>
<li>Works in Quick Chat, the chat bubble, quiz questions, hints and solutions. TTS reads formulas as words.</li>
</ul>
<hr />
<h2><a name="sec35"></a>10. Hub, Meetings, Untangling &amp; Global Hotkeys</h2>
<h3><a name="sec36"></a>10.1. 🏆 Ted Hub (Gamification)</h3>
<ul>
<li><strong>Weekly progress bar 0–100%:</strong> every Monday it restarts at <strong>50% (Level 5)</strong>. <strong>Level</strong> = ⌈% / 10⌉ (1 to 10). Study/work (Pomodoro, finished tasks, exercises) adds %; a day under 20 XP costs 5%; un-ticking a finished task takes it back.</li>
<li><strong>6 stats</strong> (⚡ Energy, 📚 Data, 🎓 Learning, 🖥 Screen load, 🎈 Engagement / Relationships, 💚 Health): <strong>cumulative within the week</strong>, also starting from 50 every Monday. Hover a stat to see how it is computed.</li>
<li><strong>53 badges:</strong> unlocked when their condition is met; once unlocked a badge is <strong>permanent</strong> and the weekly reset never locks it again. The Hub always shows every badge you have ever unlocked.</li>
<li><strong>Weekly log:</strong> stores each week's final %, peak level, stats and badges.</li>
<li><strong>🎒 Outing / family / travel button:</strong> manually log an outing (pick today or a few days back; capped per day). Rest creates no XP but raises the <strong>Health</strong> and <strong>Engagement</strong> stats.</li>
<li><strong>How to open:</strong> Dashboard → <strong>🏆 Ted Hub</strong>, right-click menu / system tray, or <code>Ctrl+Alt+G</code>. A level chip appears next to the character.</li>
<li><strong>Privacy:</strong> Ted does not track your keyboard, mouse or screen. Signals come from when Ted runs/quits, focus sessions, tasks and exercises it already knows.</li>
</ul>
<h3><a name="sec37"></a>10.2. 🎭 Character Gallery &amp; unlocks</h3>
<ul>
<li>Open Dashboard → <strong>🎭 Characters</strong> (also reachable from the right-click menu, system tray or Settings). Every character change goes through this gallery.</li>
<li>The 6 default animals are <strong>always free</strong>. On top of them there are <strong>36 characters</strong> in 6 packs, each with its <strong>own unlock condition</strong>: number of unlocked badges, one specific badge, or a lifetime stat (Deep Work sessions, focus minutes, finished tasks, quiz answers, Untangle sessions, highest level reached, day streak, outings, total XP...).</li>
<li>Locked characters show the condition still missing. Conditions are re-checked each time the Hub refreshes; a newly unlocked character triggers a notification. Unlocked is <strong>permanent</strong> (a lower weekly level never locks it again).</li>
</ul>
<h3><a name="sec38"></a>10.3. 👥 Meeting / Study-group mode</h3>
<ul>
<li>Used <strong>instead of Deep Work</strong> for team meetings, study groups or classes with a teacher.</li>
<li><strong>Start:</strong> right-click menu → <strong>👥 Start Meeting / Study group</strong>, system tray, Dashboard, or <code>Ctrl+Alt+M</code> (press again to end). The topic popup is <strong>optional</strong> (type: Team meeting / Study group / Class with teacher / Other); press <strong>Skip, start now</strong> if you do not need it.</li>
<li>The clock <strong>counts up</strong> (no countdown). Mindful pings and Untangle suggestions are paused during the meeting.</li>
<li>XP 1 per 10 minutes (max 12 XP/day), a strong boost to <strong>Engagement / Relationships</strong>, and 3 dedicated badges. AI Brain only receives numbers (sessions, minutes), <strong>never the topic</strong>.</li>
</ul>
<h3><a name="sec39"></a>10.4. 🎒 Health micro-break after Deep Work &amp; meetings</h3>
<ul>
<li>After every completed Deep Work session or meeting, Ted suggests <strong>one short break action</strong> (drink water, stand and stretch, 20-20-20 eye rest, breathing...). The suggestion also appears during the automatic break right after a Deep Work session.</li>
<li>It never appears in the middle of Deep Work or a meeting, and shows <strong>once</strong> per completed session. It can be switched off in Settings.</li>
<li>Press <code>✅ Done</code> to record it (adds to the <strong>Health</strong> stat with a daily cap, <strong>no</strong> XP) or <code>⏭ Skip</code>. Suggestions come from AI Brain (skill <code>ted-health-break</code>); when AI Brain is unavailable Ted uses offline suggestions.</li>
</ul>
<h3><a name="sec40"></a>10.5. 🧶 Idea Untangling</h3>
<ul>
<li>A conversation that unravels a messy idea into clear steps. Open it with <code>Ctrl+Alt+Space</code>, the right-click menu, or the suggestion bubble.</li>
<li><strong>Summarize &amp; Critique:</strong> AI Brain returns a summary, a flow diagram highlighting the missing step, the gaps and the next steps.</li>
<li><strong>Notes:</strong> press <strong>Save to task notes</strong> (appended to the task's notes) or <strong>➕ Create next-step task</strong>.</li>
<li>Automatic suggestions: at most 2 per day, at least 90 minutes apart, at most 1 per task per day; can be turned off with one switch.</li>
</ul>
<h3><a name="sec41"></a>10.6. ⌨️ Global hotkeys</h3>
<p>Edit them in Dashboard → Settings → <strong>⌨️ Hotkeys</strong>: click a field and press the new combination (needs Ctrl / Alt / ⌘ / ⌃), enable/disable each key, <strong>↺ Restore all</strong>.</p>
<table width="100%" cellspacing="0" cellpadding="8">
<thead>
<tr>
<th>Action</th>
<th>Windows / Linux</th>
<th>macOS</th>
</tr>
</thead>
<tbody>
<tr>
<td>🧩 Untangle an idea</td>
<td><code>Ctrl+Alt+Space</code></td>
<td><code>⌘⌥⌃Space</code></td>
</tr>
<tr>
<td>⏸ Start / Pause Pomodoro</td>
<td><code>Ctrl+Alt+P</code></td>
<td><code>⌃⌥P</code></td>
</tr>
<tr>
<td>⏹ Stop focus session</td>
<td><code>Ctrl+Alt+X</code></td>
<td><code>⌃⌥X</code></td>
</tr>
<tr>
<td>☕ Start a short break</td>
<td><code>Ctrl+Alt+B</code></td>
<td><code>⌃⌥B</code></td>
</tr>
<tr>
<td>📋 Open Dashboard</td>
<td><code>Ctrl+Alt+D</code></td>
<td><code>⌃⌥D</code></td>
</tr>
<tr>
<td>💬 Open quick chat with Ted</td>
<td><code>Ctrl+Alt+C</code></td>
<td><code>⌃⌥C</code></td>
</tr>
<tr>
<td>🅿️ Quick-park an idea</td>
<td><code>Ctrl+Alt+N</code></td>
<td><code>⌃⌥N</code></td>
</tr>
<tr>
<td>🐾 Show / Hide Ted</td>
<td><code>Ctrl+Alt+H</code></td>
<td><code>⌃⌥H</code></td>
</tr>
<tr>
<td>🏆 Open Companion Hub</td>
<td><code>Ctrl+Alt+G</code></td>
<td><code>⌃⌥G</code></td>
</tr>
<tr>
<td>👥 Start / End Meeting – Study group</td>
<td><code>Ctrl+Alt+M</code></td>
<td><code>⌃⌥M</code></td>
</tr>
</tbody>
</table>
<p>A combination that clashes with another Ted action or is already taken by an app/the system is rejected and the old key is kept. If a global key cannot be registered, it only works while Ted is in the foreground.</p>
<h3><a name="sec42"></a>10.7. 🧠 Growth reports sent to AI Brain</h3>
<ul>
<li>Ted sends AI Brain daily/weekly reports (skill <code>ted-growth-hub</code>) with %, level, the 6 stats and badges so AI Brain can encourage you, advise you and keep a growth journal.</li>
<li><strong>Privacy:</strong> reports <strong>contain aggregate counts only</strong> such as sessions, minutes and breaks. They never include task content, meeting topics, notes, Untangle content, or any keyboard, mouse or screen data.</li>
<li>When offline, reports are queued and re-sent automatically once the connection is back.</li>
</ul>
<hr />
<h2><a name="sec34"></a>11. Glossary of Terms (A–Z)</h2>
<table width="100%" cellspacing="0" cellpadding="8">
<thead>
<tr>
<th>Term</th>
<th>Category</th>
<th>Definition</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Ambient Audio</strong></td>
<td>Sound</td>
<td>Continuous background rain audio designed to block acoustic distractions and induce focus.</td>
</tr>
<tr>
<td><strong>Brain Dump</strong></td>
<td>Productivity</td>
<td>Rapidly transcribing racing thoughts onto paper or digital parking lots to clear mental RAM.</td>
</tr>
<tr>
<td><strong>Context Menu</strong></td>
<td>UI</td>
<td>The popup menu appearing upon right-clicking the pet or tray icon.</td>
</tr>
<tr>
<td><strong>Daily Journal</strong></td>
<td>Productivity</td>
<td>An evening reflection log for recording daily wins, blockers, and cognitive insights.</td>
</tr>
<tr>
<td><strong>Deep Work</strong></td>
<td>Core Concept</td>
<td>Professional activities performed in a state of distraction-free concentration.</td>
</tr>
<tr>
<td><strong>FastMCP</strong></td>
<td>Architecture</td>
<td>Model Context Protocol server enabling AI agents to invoke native desktop tools.</td>
</tr>
<tr>
<td><strong>Focus Session</strong></td>
<td>Timer</td>
<td>A dedicated 25-minute countdown focused entirely on a single defined task.</td>
</tr>
<tr>
<td><strong>AI Brain (Cloud / VPS)</strong></td>
<td>AI</td>
<td>The autonomous agent intelligence developed by Nous Research. Supports running on Cloud VPS (24/7) or locally, storing long-term memories without local-only restrictions.</td>
</tr>
<tr>
<td><strong>Intent Locking</strong></td>
<td>Technique</td>
<td>Formulating and locking in a single, concrete deliverable before a timer starts.</td>
</tr>
<tr>
<td><strong>Leitner Box</strong></td>
<td>Learning</td>
<td>A spaced repetition methodology partitioning review cards into graduated mastery bins.</td>
</tr>
<tr>
<td><strong>Local-First &amp; Hybrid</strong></td>
<td>Architecture</td>
<td>Architecture combining zero-latency client caching with persistent long-term cloud/VPS brain memory.</td>
</tr>
<tr>
<td><strong>Mindful Ping</strong></td>
<td>Timer</td>
<td>Gentle periodic check-ins verifying if your current activity aligns with your intended task.</td>
</tr>
<tr>
<td><strong>Parking Lot</strong></td>
<td>Productivity</td>
<td>A holding bin for spontaneous ideas that would otherwise break focus during Deep Work.</td>
</tr>
<tr>
<td><strong>Pomodoro</strong></td>
<td>Technique</td>
<td>Time management method dividing work into 25-minute work blocks and 5-minute rests.</td>
</tr>
<tr>
<td><strong>Proactive Nudge</strong></td>
<td>AI</td>
<td>Autonomous contextual reminders sent by AI Brain based on upcoming deadlines or events.</td>
</tr>
<tr>
<td><strong>Rocks</strong></td>
<td>Productivity</td>
<td>3–5 high-priority strategic goals that must be protected from being squeezed out by minor tasks.</td>
</tr>
<tr>
<td><strong>Skin / Chibi</strong></td>
<td>UI</td>
<td>Visual character theme (Cat, Owl, Panda, Shiba, Bunny, Penguin) representing Ted.</td>
</tr>
<tr>
<td><strong>Spaced Repetition (SRS)</strong></td>
<td>Learning</td>
<td>Reviewing learning materials at scientifically increasing intervals for permanent retention.</td>
</tr>
<tr>
<td><strong>System Tray</strong></td>
<td>OS</td>
<td>The taskbar notification area in Windows or menu bar status icon area in macOS.</td>
</tr>
</tbody>
</table>
"""
