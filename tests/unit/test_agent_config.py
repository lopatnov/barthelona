"""Agent-config hygiene (.claude/rules/agent-config.md): instruction budget, scoped rules, frontmatter."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DIR = ROOT / ".claude"
_spec = importlib.util.spec_from_file_location(
    "sync_agent_configs", ROOT / "scripts" / "sync_agent_configs.py"
)
assert _spec is not None
assert _spec.loader is not None
_sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sync)
WRITE_TOOLS: frozenset[str] = _sync.WRITE_TOOLS  # one write-tool set, shared with the Codex mirror sync
# Owner-reviewed limits. Raise them only in an explicit diff; first move detail out of instructions.
MAX_ALWAYS_LOADED_BYTES = 22_000
MAX_ALWAYS_LOADED_LINES = 200  # docs-adr rule: AGENTS.md + CLAUDE.md under about 200 lines together
MAX_RULE_BYTES = 5_000
MAX_DESCRIPTION_CHARS = 500
READ_ONLY_PROSE = re.compile(r"(never|do not) (modify|edit) files", re.IGNORECASE)
HINT = "Move detail into a skill, a path-scoped rule or docs/ (see .claude/rules/agent-config.md)."


def _frontmatter(path: Path) -> dict[str, str]:
    """Top-level `key: value` lines of the frontmatter (same reader as scripts/sync_agent_configs.py)."""
    lines = path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return meta
        if line and not line.startswith((" ", "\t", "-", "#")) and ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip("\"'")
    return {}


def _csv(value: str) -> set[str]:
    return {t.strip() for t in value.split(",") if t.strip()}


def _rules() -> list[Path]:
    return sorted((CLAUDE_DIR / "rules").glob("*.md"))


def _skills() -> list[Path]:
    return sorted((CLAUDE_DIR / "skills").glob("*/SKILL.md"))


def _agents() -> list[Path]:
    return sorted(p for p in (CLAUDE_DIR / "agents").glob("*.md") if p.name.lower() != "readme.md")


def _always_loaded() -> list[Path]:
    files = [ROOT / "AGENTS.md", ROOT / "CLAUDE.md"]
    for line in (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines():
        target = (ROOT / line[1:].strip()).resolve() if line.startswith("@") else None
        if target and target.is_file() and target not in {f.resolve() for f in files}:
            files.append(target)
    return files + [p for p in _rules() if "paths" not in _frontmatter(p)]


def test_always_loaded_instructions_within_budget() -> None:
    files = _always_loaded()
    size = {f.name: f.stat().st_size for f in files}
    lines = {f.name: len(f.read_text(encoding="utf-8").splitlines()) for f in files}
    assert sum(size.values()) <= MAX_ALWAYS_LOADED_BYTES, f"{size} bytes. {HINT}"
    assert sum(lines.values()) <= MAX_ALWAYS_LOADED_LINES, f"{lines} lines. {HINT}"


@pytest.mark.parametrize("rule", _rules(), ids=lambda p: p.name)
def test_rule_is_path_scoped_and_small(rule: Path) -> None:
    assert "paths" in _frontmatter(rule), f"{rule.name}: unscoped rules load on every turn; add `paths:`"
    assert rule.stat().st_size <= MAX_RULE_BYTES, f"{rule.name}: split it or move a procedure into a skill"


@pytest.mark.parametrize("path", _skills() + _agents(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_skill_and_agent_frontmatter(path: Path) -> None:
    meta = _frontmatter(path)
    expected = path.parent.name if path.name == "SKILL.md" else path.stem
    assert meta.get("name") == expected, f"{path}: frontmatter name must be {expected!r}"
    description = meta.get("description", "")
    assert description, f"{path}: add a description (when to call it, what it returns)"
    assert len(description) <= MAX_DESCRIPTION_CHARS, f"{path}: description is too long. {HINT}"


@pytest.mark.parametrize("agent", _agents(), ids=lambda p: p.stem)
def test_read_only_agents_say_so_in_their_body(agent: Path) -> None:
    """Codex sees only the body and sandbox_mode, not the Claude tool lists."""
    meta = _frontmatter(agent)
    tools, denied = _csv(meta.get("tools", "")), _csv(meta.get("disallowedTools", ""))
    if (tools and not tools & WRITE_TOOLS) or {"Edit", "Write"} <= denied:
        text = agent.read_text(encoding="utf-8")
        assert READ_ONLY_PROSE.search(text), f"{agent.name}: say 'Never modify files.' in the body"
        mirror = ROOT / ".codex" / "agents" / f"{agent.stem}.toml"
        assert 'sandbox_mode = "read-only"' in mirror.read_text(encoding="utf-8"), (
            f"{mirror.name}: not read-only"
        )


def test_every_skill_and_agent_is_routed_in_agents_md() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    names = [p.parent.name for p in _skills()] + [p.stem for p in _agents()]
    missing = [n for n in names if f"`{n}`" not in text]
    assert not missing, f"add {missing} to the 'Who to call' table in AGENTS.md"
