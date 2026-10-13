"""Print one section of the local assembler docs in asm_doc/ as plain text.

Usage (from the repo root, barthelona env active):
    python .claude/skills/asm-docs/extract.py nasm-toc
    python .claude/skills/asm-docs/extract.py nasm 5.3          # NASM 3.02 section (also 13, F.1.1, ...)
    python .claude/skills/asm-docs/extract.py insn MOVZX        # NASM Appendix F rows for a mnemonic
    python .claude/skills/asm-docs/extract.py html fasm/manual.htm 2.3.3
    python .claude/skills/asm-docs/extract.py html binutils/as.htm i386_002dRegs
    python .claude/skills/asm-docs/extract.py ids binutils/LD.htm   # list anchor ids with headings

Output is capped (default 400 lines, --max N to change). Read-only; never modifies asm_doc/.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "asm_doc"
NASM_TXT = DOCS / "nasm-3.02-xdoc" / "doc" / "nasmdoc.txt"
HEADING_RE = re.compile(r"^\s{0,3}(?:(Chapter|Appendix) ([0-9A-Z]+):|([0-9A-F]+(?:\.[0-9]+)+) )")


def _out(lines: list[str], limit: int) -> None:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    for line in lines[:limit]:
        print(line)
    if len(lines) > limit:
        print(f"... [{len(lines) - limit} more lines; use --max]")


def _nasm_lines() -> list[str]:
    return NASM_TXT.read_text(encoding="utf-8", errors="replace").splitlines()


def _heading_id(line: str) -> str | None:
    m = HEADING_RE.match(line)
    if not m:
        return None
    return m.group(2) or m.group(3)


def nasm_toc(limit: int) -> None:
    rows = []
    for no, line in enumerate(_nasm_lines(), 1):
        m = HEADING_RE.match(line)
        if m and (m.group(1) or line.lstrip().count(".") <= 2):
            rows.append(f"{no:>6}: {line.strip()}")
    _out(rows, limit)


def nasm_section(sec: str, limit: int) -> None:
    lines = _nasm_lines()
    depth = sec.count(".")
    start = None
    for i, line in enumerate(lines):
        hid = _heading_id(line)
        if hid == sec:
            start = i
            break
    if start is None:
        sys.exit(f"section {sec!r} not found; try: extract.py nasm-toc")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        hid = _heading_id(lines[j])
        if hid and hid.count(".") <= depth:
            end = j
            break
    _out([f"[NASM 3.02 {sec}] nasmdoc.txt lines {start + 1}-{end}", *lines[start:end]], limit)


def nasm_insn(mnemonic: str, limit: int) -> None:
    lines = _nasm_lines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("Appendix F:"))
    pat = re.compile(rf"^\s+{re.escape(mnemonic.upper())}\s")
    rows = [ln.rstrip() for ln in lines[start:] if pat.match(ln)]
    _out(rows or [f"{mnemonic!r} not found in Appendix F"], limit)


def _soup(rel: str) -> BeautifulSoup:
    from bs4 import BeautifulSoup

    path = (DOCS / rel).resolve()
    if not path.is_relative_to(DOCS.resolve()):  # never read outside asm_doc/
        sys.exit(f"refusing to read outside asm_doc/: {rel}")
    if not path.is_file():
        sys.exit(f"not found: {path}")
    return BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "lxml")


def html_ids(rel: str, limit: int) -> None:
    soup = _soup(rel)
    rows = []
    for el in soup.find_all(id=True):
        text = " ".join(el.get_text(" ", strip=True).split())[:90]
        if el.name in {"h1", "h2", "h3", "h4", "h5", "div", "a", "span"}:
            rows.append(f"{el['id']:<40} <{el.name}> {text}")
    _out(rows, limit)


def html_section(rel: str, anchor: str, limit: int) -> None:
    soup = _soup(rel)
    el = soup.find(id=anchor)
    if el is None:
        sys.exit(f"id {anchor!r} not found in {rel}; list ids with: extract.py ids {rel}")
    if el.name == "div":  # texinfo (binutils) puts each section, with nested subsections, in a div
        for junk in el.find_all(["div", "a"], class_=re.compile(r"nav-panel|copiable-link|index-entry-id")):
            junk.decompose()
        blocks = ["h2", "h3", "h4", "h5", "p", "pre", "dt", "dd", "li", "tr"]
        parts = []
        for blk in el.find_all(blocks):
            outer = blk.find_parent(["p", "pre", "dd", "li", "tr"])
            if outer is not None and el in outer.parents:
                continue  # nested block: already printed as part of its outer block
            if blk.name == "pre" or blk.find("pre") is not None:
                parts.append(blk.get_text("", strip=False).strip("\n"))
            else:
                parts.append(" ".join(blk.get_text(" ", strip=True).split()))
        text = "\n".join(parts)
    else:  # fasm: heading followed by siblings until the next heading of same or higher level
        level = int(el.name[1]) if re.fullmatch(r"h[1-6]", el.name or "") else 6
        parts = [el.get_text(" ", strip=True)]
        for sib in el.find_all_next():
            if re.fullmatch(r"h[1-6]", sib.name or "") and int(sib.name[1]) <= level:
                break
            if (
                sib.name in {"p", "pre", "li", "td", "th", "h5", "h6"}
                and sib.find_parent(["p", "pre", "li"]) is None
            ):
                parts.append(sib.get_text("\n" if sib.name == "pre" else " ", strip=sib.name != "pre"))
        text = "\n".join(parts)
    lines = [ln.rstrip() for ln in text.splitlines()]
    compact: list[str] = []
    for ln in lines:
        if ln or (compact and compact[-1]):
            compact.append(ln)
    _out([f"[{rel} #{anchor}]", *compact], limit)


def main(argv: list[str]) -> None:
    limit = 400
    if "--max" in argv:
        k = argv.index("--max")
        limit = int(argv[k + 1])
        del argv[k : k + 2]
    if not argv:
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == "nasm-toc":
        nasm_toc(limit)
    elif cmd == "nasm" and len(args) == 1:
        nasm_section(args[0], limit)
    elif cmd == "insn" and len(args) == 1:
        nasm_insn(args[0], limit)
    elif cmd == "ids" and len(args) == 1:
        html_ids(args[0], limit)
    elif cmd == "html" and len(args) == 2:
        html_section(args[0], args[1], limit)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
