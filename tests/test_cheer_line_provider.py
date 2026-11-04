"""CheerLineProvider: parse pool, mượn pool module work, cổng 1/5 (rng seed), Deep Work → chỉ local, fallback khi Hermes lỗi."""

import asyncio
import random
from types import SimpleNamespace

from src.bridge.hermes_client import HermesUnavailableError
from src.core.focus_engine import FocusState
from src.modules_runtime.cheer_line_provider import BUILTIN_CHEERS, CheerLineProvider
from src.modules_runtime.module_manifest_schema import ModuleManifest


def _work(tmp_path, with_pool=True) -> ModuleManifest:
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "cheers.md").write_text("# t\n\n- Câu một\n- Câu hai\n", encoding="utf-8")
    (tmp_path / "prompts" / "cheer.md").write_text("[TED_CHEER] state={{state}} task={{task}}", encoding="utf-8")
    m = ModuleManifest(
        id="work", name="Việc", engine="work", connection="work",
        prompts={"cheers": "prompts/cheers.md", "cheer": "prompts/cheer.md"} if with_pool else {},
    )
    m.module_dir = tmp_path
    return m


def _coach() -> ModuleManifest:
    return ModuleManifest(id="thcs", name="Học", engine="coach", connection="thcs", learner_id="con")


class FakeClient:
    def __init__(self, reply="[MOOD:CHEER] Cố lên bạn ơi!", error=None):
        self.reply, self.error, self.calls = reply, error, []

    async def complete_text(self, messages, timeout=60.0):
        self.calls.append((messages, timeout))
        if self.error:
            raise self.error
        return self.reply


def _provider(manifests, client, state=FocusState.IDLE, roll=0.0):
    registry = SimpleNamespace(get=lambda i: manifests.get(i), active=lambda: None)
    pool = SimpleNamespace(for_module=lambda i: client)
    focus = SimpleNamespace(state=state, current_mood="IDLE", get_context_snapshot=lambda: {"status": state, "task": "Viết báo cáo"})
    rng = SimpleNamespace(random=lambda: roll, choice=random.Random(1).choice)
    return CheerLineProvider(registry, pool, focus_engine=focus, rng=rng)


def test_pick_local_uses_pool_and_coach_borrows_work_pool(tmp_path):
    work = _work(tmp_path)
    p = _provider({"work": work}, FakeClient())
    assert p.pick_local(work) in {"Câu một", "Câu hai"}
    assert p.pick_local(_coach()) in {"Câu một", "Câu hai"}


def test_pick_local_builtin_when_no_pool(tmp_path):
    work = _work(tmp_path, with_pool=False)
    assert _provider({"work": work}, FakeClient()).pick_local(work) in BUILTIN_CHEERS
    assert _provider({}, FakeClient()).pick_local(_coach()) in BUILTIN_CHEERS


def test_gate_is_one_in_five_with_seeded_rng(tmp_path):
    work = _work(tmp_path)
    registry = SimpleNamespace(get=lambda i: work)
    pool = SimpleNamespace(for_module=lambda i: FakeClient())
    focus = SimpleNamespace(state=FocusState.IDLE)
    p = CheerLineProvider(registry, pool, focus_engine=focus, rng=random.Random(42))
    hits = sum(p.should_ask_hermes(work) for _ in range(2000))
    assert 300 < hits < 500  # ~20%


def test_deep_work_never_asks_hermes(tmp_path):
    work = _work(tmp_path)
    client = FakeClient()
    p = _provider({"work": work}, client, state=FocusState.DEEP_WORK_RUNNING, roll=0.0)
    assert not p.should_ask_hermes(work)
    assert asyncio.run(p.cheer_text(work)) in {"Câu một", "Câu hai"}
    assert client.calls == []


def test_no_connection_means_local_only(tmp_path):
    work = _work(tmp_path)
    p = _provider({"work": work}, None)
    assert not p.should_ask_hermes(work)


def test_work_hermes_cheer_renders_prompt_and_strips_mood(tmp_path):
    work = _work(tmp_path)
    client = FakeClient()
    text = asyncio.run(_provider({"work": work}, client).cheer_text(work))
    assert text == "Cố lên bạn ơi!"
    messages, timeout = client.calls[0]
    assert messages[0]["content"] == "[TED_CHEER] state=IDLE task=Viết báo cáo" and timeout == 4.0


def test_coach_hermes_uses_plain_prompt(tmp_path):
    client = FakeClient()
    text = asyncio.run(_provider({"work": _work(tmp_path)}, client).cheer_text(_coach()))
    assert text == "Cố lên bạn ơi!"
    assert client.calls[0][0][0]["content"] == "Động viên mình 1 câu ngắn"


def test_hermes_error_or_empty_falls_back_to_local(tmp_path):
    work = _work(tmp_path)
    for client in (FakeClient(error=HermesUnavailableError("x")), FakeClient(reply="[MOOD:IDLE]   ")):
        assert asyncio.run(_provider({"work": work}, client).cheer_text(work)) in {"Câu một", "Câu hai"}
