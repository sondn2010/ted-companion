"""Bộ tiền xử lý ngắt nghỉ VieNeu (docs/tts-specs/tts-specs-v1.md): ma trận P-01..P-14, 6 trường hợp biên của §2,
từ điển phát âm (nhập / xuất JSON), exporter, CLI và việc engine chèn khoảng lặng thay vì gửi thẻ [giây] cho model."""

import asyncio
import io
import json
import time
import wave

import httpx
import pytest

from src.config import settings
from src.core import vieneu_sidecar_process_manager as pm
from src.core.vieneu_sidecar_tts_engine import VieneuSidecarTTSEngine
from src.core.vieneu_story_preprocessor import cli, effective_pauses, preprocess
from src.core.vieneu_story_preprocessor.core import lexicon_mapper
from src.core.vieneu_story_preprocessor.core.sanitizer import sanitize
from src.core.vieneu_story_preprocessor.exporters.sdk_json_exporter import to_json_chunks
from src.core.vieneu_story_preprocessor.exporters.studio_txt_exporter import to_studio_script
from src.core.vieneu_text_chunking_and_wav_concat import append_silence

SAMPLE = """ặt nước Hồ Đen vào đêm mồng một tháng Chín phẳng lặng và đen nhánh như một tấm gương bằng đá hắc diện thạch khổng lồ, phản chiếu hàng ngàn ngôi sao lấp lánh của vùng cao nguyên Scotland. Khi đoàn thuyền gỗ nhỏ lướt đi êm ru không cần mái chèo dưới sự dẫn đường của lão Hagrid khổng lồ, tòa lâu đài Hogwarts dần hiện ra sừng sững trên đỉnh vách đá dựng đứng — một quần thể đồ sộ gồm những tháp canh nhọn hoắt, những bức tường đá cổ kính rêu phong và hàng trăm ô cửa sổ rực sáng như những viên hồng ngọc treo lơ lửng giữa bầu trời đêm.
Vành nón hơi rộng, sụp xuống che khuất tầm mắt. Ngay lập tức, một giọng nói nhỏ nhẹ, khô khốc vang lên trong tâm trí cô:
Chà, một người nhà Malfoy nữa. Đã lâu rồi đấy.
Dracaena ngồi im. Thông minh. Rất thông minh, chiếc nón thì thầm. Lòng kiêu hãnh không thiếu. Tôi là một Malfoy.
"Potter, Harry!"
Harry bước lên chiếc ghế đẩu. Chiếc nón sụp xuống đầu cậu. Một giây trôi qua. Năm giây. Mười giây. Ba mươi giây.
Rồi chiếc nón hét vang:
"GRYFFINDOR!"
"""


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)   # từ điển người dùng nằm trong thư mục tạm
    return tmp_path


def _find(segments, needle):
    return next(i for i, s in enumerate(segments) if needle in s.text)


# ---------------- Tầng 1: sanitizer ----------------
def test_sanitizer_recovers_drop_cap_drops_metadata_and_marks_structure():
    paras = sanitize("1.234 từ · 5 phút đọc\nM\nặt nước phẳng lặng\n* * *\n- việc một\n2) việc hai\n...\n## Tiêu đề")
    assert [(p.kind, p.text) for p in paras] == [
        ("text", "Mặt nước phẳng lặng."), ("scene_break", ""), ("list_item", "việc một."),
        ("list_item", "2, việc hai."), ("text", "Tiêu đề.")]
    assert sanitize("ặt nước Hồ Đen.")[0].text == "Mặt nước Hồ Đen."
    assert sanitize("“Xin chào” — anh nói…")[0].text == '"Xin chào" — anh nói...'


# ---------------- Tầng 3: ma trận ngắt nghỉ ----------------
def test_pause_matrix_by_sentence_length_and_punctuation():
    short = "Cô ấy mở cửa bước vào phòng."                                            # 7 từ → P-01
    standard = "Ngoài trời mưa vẫn rơi đều đặn trên mái tôn cũ kỹ của căn nhà nhỏ ven sông."  # 17 từ → P-02
    epic = " ".join(["Con đường mòn dài"] * 9) + "."                                   # 36 từ → P-03
    segs = preprocess(f"Mở đầu thôi. {short} {standard} {epic} Có thật không? Kết thúc.")
    pauses = effective_pauses(segs)
    assert pauses == [0.75, 0.35, 0.55, 0.85, 0.65, 0.0]   # câu ≤ 4 từ đầu đoạn → P-04; ? → P-06; cuối bài → 0


def test_paragraph_scene_break_and_list_items():
    segs = preprocess("Đoạn một có vài từ ở đây.\nĐoạn hai cũng có vài từ.\n***\nSau đổi cảnh nè bạn ơi.")
    assert effective_pauses(segs) == [1.0, 1.8, 0.0]   # P-13, P-14
    items = preprocess("Hôm nay bạn có:\n- Họp nhóm lúc chín giờ sáng\n- Gửi báo cáo tuần\nChúc bạn một ngày vui vẻ.")
    assert effective_pauses(items)[1:] == [0.55, 1.0, 0.0]   # giữa các gạch đầu dòng nghỉ ngắn hơn xuống đoạn


def test_dashes_breath_comma_and_mid_ellipsis():
    pair = preprocess("Lâu đài — nơi ông từng sống — giờ đã đổ nát hoàn toàn.")
    assert [(s.text, p) for s, p in zip(pair, effective_pauses(pair))] == [
        ("Lâu đài...", 0.3), ("nơi ông từng sống...", 0.35), ("giờ đã đổ nát hoàn toàn.", 0.0)]
    long_clause = " ".join(["đoàn người"] * 10)
    breath = preprocess(f"Khi {long_clause}, thì trời bắt đầu đổ mưa.")
    assert breath[0].text.endswith(",") and effective_pauses(breath)[0] == 0.3   # P-10
    no_breath = preprocess("Sáng nay trời đẹp, mình đi dạo.")
    assert len(no_breath) == 1   # dấu phẩy nối cụm ngắn: KHÔNG chèn ngắt cứng
    ellipsis = preprocess("Hoặc ít nhất... con biết rất rõ điều đó.")
    assert [s.text for s in ellipsis] == ["Hoặc ít nhất...", "con biết rất rõ điều đó."]


def test_progressive_countdown():
    segs = preprocess(SAMPLE)
    start = _find(segs, "Một giây")
    run = segs[start:start + 4]
    assert [s.text for s in run] == ["Một giây trôi qua...", "Năm giây...", "Mười giây...", "Ba mươi giây..."]
    assert effective_pauses(segs)[start:start + 4] == [0.6, 0.85, 1.1, 1.4]
    assert {s.role for s in run} == {"narration_countdown"} and run[0].speed == 0.92
    # câu ngắn liên tiếp nhưng không đếm thời gian (câu trả lời của Ted) → không kéo dài
    plain = preprocess("Được rồi. Mình hiểu. Để mình xem. Bạn chờ nhé.")
    assert all(s.role == "narration" for s in plain)


# ---------------- Tầng 2: hội thoại ----------------
def test_shout_and_roll_call():
    segs = preprocess(SAMPLE)
    pauses = effective_pauses(segs)
    i = _find(segs, "Pót tơ")
    assert segs[i].text == "Pót tơ..." and segs[i + 1].text == "He ri!" and pauses[i] == 0.25
    assert pauses[i - 1] >= 0.5 and segs[i].role == "dialogue_shout"
    g = _find(segs, "phin đo")
    assert segs[g].text == "Gờ ríp phin đo!" and segs[g].speed == 0.95   # IN HOA → thường; "hét vang" → 0.95
    assert pauses[g - 1] == 0.5 and segs[g - 1].text == "Rồi chiếc nón hét vang:"


def test_inner_voice_detector():
    segs = preprocess(SAMPLE)
    roles = {s.text: s.role for s in segs}
    assert roles["Chà..."] == roles["một người nhà Man phoi nữa."] == "inner_voice"
    assert roles["Đờ ra xê na ngồi im."] == "narration"
    assert roles["Rất thông minh."] == "inner_voice" and roles["Chiếc nón thì thầm."] == "narration"
    assert roles["Tôi là một Man phoi."] == "inner_voice"
    colon = _find(segs, "trong tâm trí cô:")
    assert effective_pauses(segs)[colon] == 0.45 and segs[colon + 1].speed == 0.92


def test_split_dialogue_linker_tone_and_embedded_quote():
    segs = preprocess('"Trần nhà không có thật đâu," Hermione thì thầm. "Nó chỉ được yểm bùa thôi."')
    assert [(s.speaker, s.role, s.text) for s in segs] == [
        ("Hermione", "dialogue", "Trần nhà không có thật đâu."),
        ("Narrator", "narration", "Hơ mai ơ ni thì thầm."),
        ("Hermione", "dialogue", "Nó chỉ được yểm bùa thôi.")]
    assert effective_pauses(segs)[:2] == [0.35, 0.35]   # P-11
    laugh = preprocess('"Ha ha, đúng thế," Ron bật cười.')
    assert laugh[0].emotion == "cười" and laugh[0].speed == 1.02
    embedded = preprocess('Câu nói "Chính xác là người con phải trở thành" vẫn vương lại trong đầu cô.')
    assert {s.role for s in embedded} == {"narration"}
    assert [s.text for s in embedded][-1] == "vẫn vương lại trong đầu cô."
    assert effective_pauses(embedded)[:2] == [0.2, 0.25]
    inline = preprocess('Bạn bấm nút "Lưu" để hoàn tất.')
    assert [s.text for s in inline] == ["Bạn bấm nút Lưu để hoàn tất."]


# ---------------- Tầng 4: từ điển phát âm ----------------
def test_lexicon_mapping_caps_and_acronym_case(isolated_home):
    assert preprocess("Harry Potter có cuộc meeting với Malfoy.")[0].text == "He ri pót tơ có cuộc mít tinh với Man phoi."
    assert preprocess("Ai cũng biết AI là gì.")[0].text == "Ai cũng biết ây ai là gì."   # "ai" tiếng Việt giữ nguyên
    assert preprocess("Harry Potter is here.")[0].text == "Harry Potter is here."   # văn bản tiếng Anh: không phiên âm


def test_lexicon_import_export_roundtrip(isolated_home, tmp_path):
    src = tmp_path / "in.json"
    src.write_text(json.dumps({"Ted": "tét", "Harry Potter": "ha ri pót tơ"}, ensure_ascii=False), encoding="utf-8")
    assert lexicon_mapper.import_lexicon(src) == 2
    assert preprocess("Ted gặp Harry Potter rồi.")[0].text == "Tét gặp Ha ri pót tơ rồi."   # người dùng thắng mục đi kèm
    out = tmp_path / "out.json"
    count = lexicon_mapper.export_lexicon(out)
    exported = json.loads(out.read_text(encoding="utf-8"))
    assert count == len(exported) and exported["Ted"] == "tét" and exported["Malfoy"] == "man phoi"
    bad = tmp_path / "bad.json"
    bad.write_text('["không phải dict"]', encoding="utf-8")
    with pytest.raises(ValueError):
        lexicon_mapper.import_lexicon(bad)
    (isolated_home / "custom_lexicon.json").write_text("{hỏng", encoding="utf-8")
    assert preprocess("Malfoy đến.")[0].text == "Man phoi đến."   # file người dùng hỏng: vẫn đọc bằng từ điển đi kèm


# ---------------- Tầng 5: exporter + CLI ----------------
def test_exporters_follow_spec_formats():
    segs = preprocess(SAMPLE)
    script = to_studio_script(segs)
    assert script.startswith("Người dẫn: Mặt nước Hồ Đen")
    assert "Nội tâm: Chà... [0.35] một người nhà Man phoi nữa. [0.35]" in script and "[1.4]" in script
    chunks = to_json_chunks(segs, voices={"Narrator": "Thiện Minh"}, prefix="ch01_")
    first = chunks[0]
    assert first["chunk_id"] == "ch01_p01_s01" and first["voice_preset"] == "Thiện Minh"
    assert set(first) >= {"speaker", "role_type", "text", "speed", "pause_before_sec", "pause_after_sec"}


def test_cli_processes_file_and_lexicon(tmp_path, capsys):
    src = tmp_path / "chuong01.md"
    src.write_text(SAMPLE, encoding="utf-8")
    assert cli.main([str(tmp_path), "-o", str(tmp_path / "out"), "--export-lexicon", str(tmp_path / "lex.json")]) == 0
    assert (tmp_path / "out" / "chuong01.studio.txt").read_text(encoding="utf-8").startswith("Người dẫn:")
    assert json.loads((tmp_path / "out" / "chuong01.json").read_text(encoding="utf-8"))[0]["chunk_id"] == "chuong01_p01_s01"
    assert "Malfoy" in json.loads((tmp_path / "lex.json").read_text(encoding="utf-8"))


def test_chapter_preprocessing_is_fast_on_cpu():
    chapter = "\n".join([SAMPLE] * 10)   # ~ một chương dài
    preprocess(chapter)   # nạp cấu hình / biên dịch regex
    started = time.perf_counter()
    preprocess(chapter)
    assert time.perf_counter() - started < 1.0


# ---------------- Engine: chèn khoảng lặng, không gửi thẻ ----------------
def _wav(frames: int, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x01\x00" * frames)
    return buf.getvalue()


def test_append_silence_adds_exact_frames():
    with wave.open(io.BytesIO(append_silence(_wav(100), 0.5))) as wf:
        assert wf.getnframes() == 100 + 12000


def test_engine_sends_plain_segments_and_inserts_silence(monkeypatch):
    monkeypatch.setattr(settings, "vieneu_voices", {})
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append((body["input"], body["speed"]))
        return httpx.Response(200, content=_wav(100))

    class Mgr:
        def ensure_running(self, model_id, precision="fp32"):
            return pm.SidecarEndpoint("http://127.0.0.1:1/v1", "t", model_id)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    engine = VieneuSidecarTTSEngine("vieneu-v3-nano", manager=Mgr())
    out = asyncio.run(engine.synthesize("Chào bạn nhé.\nMột giây. Năm giây. Mười giây.", "", 1.0, http_client=client))
    assert [t for t, _ in sent] == ["Chào bạn nhé.", "Một giây...", "Năm giây...", "Mười giây..."]
    assert not any("[" in t or "<" in t for t, _ in sent)   # VieNeu đọc thẻ thành tiếng → không bao giờ gửi
    assert sent[1][1] == pytest.approx(0.92)
    silence = round((1.0 + 0.6 + 0.85) * 24000)   # xuống đoạn + đếm giây tăng tiến; khúc cuối không có đuôi lặng
    with wave.open(io.BytesIO(out)) as wf:
        assert wf.getnframes() == 100 * 4 + silence


def test_tts_service_gives_structured_text_to_offline_engine(monkeypatch):
    from src.core.tts_service import LocalEmbeddedTTSEngine, TTSService
    seen = []

    class Engine(LocalEmbeddedTTSEngine):
        async def synthesize(self, text, voice, speed=1.0, http_client=None, should_continue=None, on_chunk=None):
            seen.append(text)
            return b""

    svc = TTSService.__new__(TTSService)   # không cần Qt player cho bước này
    monkeypatch.setattr(svc, "get_engine", lambda *a, **k: Engine(), raising=False)
    monkeypatch.setattr(svc, "pick_voice", lambda lang: "", raising=False)
    asyncio.run(TTSService.synthesize(svc, '**Chào** bạn 👋\n"Xin chào" — Ted nói…', lang="vi"))
    assert seen == ['Chào bạn 👋\n"Xin chào" — Ted nói…']
