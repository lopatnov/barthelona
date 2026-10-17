"""Mirror the Claude Code agent configuration into Codex's formats.

Source of truth (edit these):
    .claude/skills/<name>/**   -> mirrored byte-for-byte to .agents/skills/<name>/**   (Codex skills)
    .claude/agents/<name>.md   -> converted to .codex/agents/<name>.toml               (Codex agents)
Shared project instructions live in AGENTS.md (read by Codex; imported by CLAUDE.md), so no
conversion is needed for them. .codex/config.toml is owned by Codex and never touched here.

Usage (repo root):
    python scripts/sync_agent_configs.py           # write the mirror
    python scripts/sync_agent_configs.py --check   # exit 1 if the mirror is stale (used by tests)
The Claude Code PostToolUse hook runs it automatically after edits under .claude/skills or .claude/agents.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_SRC = ROOT / ".claude" / "skills"
SKILLS_DST = ROOT / ".agents" / "skills"
AGENTS_SRC = ROOT / ".claude" / "agents"
AGENTS_DST = ROOT / ".codex" / "agents"
WRITE_TOOLS = frozenset({"Edit", "Write", "NotebookEdit", "MultiEdit"})  # shared with the tests
HEADER = "# GENERATED from .claude/agents/{name}.md by scripts/sync_agent_configs.py - do not edit.\n"


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Minimal frontmatter reader: top-level `key: value` lines only (enough for name/description)."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict[str, str] = {}
    for i in range(1, len(lines)):
        line = lines[i]
        if line.strip() == "---":
            return meta, "\n".join(lines[i + 1 :]).strip("\n") + "\n"
        if line and not line.startswith((" ", "\t", "-", "#")) and ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"').strip("'")
    return {}, text


def _toml_basic(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_multiline(value: str) -> str:
    if "'''" not in value:
        return "'''\n" + value + "'''"  # literal string: backslashes kept as-is
    escaped = value.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return '"""\n' + escaped + '"""'


def expected_files() -> dict[Path, bytes]:
    out: dict[Path, bytes] = {}
    for src in sorted(SKILLS_SRC.rglob("*")):
        if src.is_file() and "__pycache__" not in src.parts:
            out[SKILLS_DST / src.relative_to(SKILLS_SRC)] = src.read_bytes()
    for src in sorted(AGENTS_SRC.glob("*.md")):
        if src.name.lower() == "readme.md":
            continue
        meta, body = _split_frontmatter(src.read_text(encoding="utf-8"))
        name = meta.get("name", src.stem)
        # Claude `tools`/`disallowedTools` do not exist in Codex; keep read-only agents read-only there.
        tools = {t.strip() for t in meta.get("tools", "").split(",") if t.strip()}
        denied = {t.strip() for t in meta.get("disallowedTools", "").split(",") if t.strip()}
        read_only = (bool(tools) and not (tools & WRITE_TOOLS)) or {"Edit", "Write"} <= denied
        toml = (
            HEADER.format(name=src.stem)
            + f"name = {_toml_basic(name)}\n"
            + f"description = {_toml_basic(meta.get('description', ''))}\n"
            + ('sandbox_mode = "read-only"\n' if read_only else "")
            + f"developer_instructions = {_toml_multiline(body)}\n"
        )
        out[AGENTS_DST / f"{src.stem}.toml"] = toml.encode("utf-8")
    return out


def existing_files() -> set[Path]:
    found: set[Path] = set()
    if SKILLS_DST.is_dir():
        found |= {p for p in SKILLS_DST.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    if AGENTS_DST.is_dir():
        found |= set(AGENTS_DST.glob("*.toml"))
    return found


def _inside_mirror(path: Path) -> bool:
    # Compare with the repo-local roots as spelled, not resolved: a symlinked .agents/ or
    # .codex/agents/ must not turn an outside directory into an accepted mirror root.
    resolved = path.resolve()
    return any(resolved.is_relative_to(root) for root in (SKILLS_DST, AGENTS_DST))


def _check(stale: list[Path], extra: list[Path]) -> int:
    if not stale and not extra:
        print("Codex mirror is up to date")
        return 0
    for p in stale:
        print(f"stale:   {p.relative_to(ROOT)}")
    for p in extra:
        print(f"orphan:  {p.relative_to(ROOT)}")
    print("Codex mirror is out of date: run python scripts/sync_agent_configs.py")
    return 1


def _sync(want: dict[Path, bytes], stale: list[Path], extra: list[Path]) -> int:
    escaping = [p for p in (*stale, *extra) if not _inside_mirror(p)]
    if escaping:
        # A symlinked skill file or directory would make the sync write or delete outside the repo.
        for p in escaping:
            print(f"refusing: {p} resolves outside {SKILLS_DST} and {AGENTS_DST}")
        return 1
    for p in stale:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(want[p])
    for p in extra:
        p.unlink()
    print(f"synced Codex mirror: {len(stale)} written, {len(extra)} removed")
    return 0


def main(argv: list[str]) -> int:
    want = expected_files()
    stale = [p for p, data in want.items() if not p.is_file() or p.read_bytes() != data]
    extra = sorted(existing_files() - set(want))
    return _check(stale, extra) if "--check" in argv else _sync(want, stale, extra)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
