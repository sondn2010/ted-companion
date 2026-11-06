"""Renderer {{var}}: giữ biến lạ và dấu { } của JSON; parse bullet; đọc prompt trong module_dir."""

from src.modules_runtime.module_manifest_schema import ModuleManifest
from src.modules_runtime.prompt_template_renderer import load_prompt, parse_bullet_lines, render_prompt


def test_renderer_keeps_unknown_vars_and_json_braces():
    tpl = 'state={{state}} x={{ unknown }} {"a": {"b": 1}}'
    assert render_prompt(tpl, {"state": "FOCUS"}) == 'state=FOCUS x={{ unknown }} {"a": {"b": 1}}'


def test_render_coerces_non_string_values():
    assert render_prompt("n={{n}}", {"n": 5}) == "n=5"


def test_parse_bullet_lines_ignores_headings_and_blank():
    md = "# Tiêu đề\n\n- một\n* hai\n1. ba\ntext thường\n-   \n"
    assert parse_bullet_lines(md) == ["một", "hai", "ba"]


def test_load_prompt_renders_and_returns_none_for_missing(tmp_path):
    (tmp_path / "p.md").write_text("hi {{who}}", encoding="utf-8")
    m = ModuleManifest(id="w", name="W", engine="work", connection="c", prompts={"a": "p.md", "b": "none.md"})
    m.module_dir = tmp_path
    assert load_prompt(m, "a", {"who": "Ted"}) == "hi Ted"
    assert load_prompt(m, "b", {}) is None
    assert load_prompt(m, "unknown", {}) is None
