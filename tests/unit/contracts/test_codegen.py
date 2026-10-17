"""Codegen golden files and the tamper gate (architecture §15.1, invariants 3 and 4)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from barthelona.contracts import CodegenError, check_generated, render_all, render_module_inc, tamper_result
from barthelona.domain.contracts import (
    ContractRegistry,
    StructDef,
    StructField,
    Symbol,
    SymbolKind,
    Visibility,
)
from barthelona.domain.enums import ABI, OS, Arch, Dialect, Linker, ObjFormat, RunEnv
from barthelona.domain.project import TargetProfile

_GOLDEN = Path(__file__).parents[2] / "codegen_golden"


def _registry(dialect: Dialect = Dialect.NASM) -> ContractRegistry:
    target = TargetProfile(
        preset="linux-x64-test",
        dialect=dialect,
        arch=Arch.X86_64,
        os=OS.LINUX,
        abi=ABI.SYSV64,
        obj_format=ObjFormat.ELF64,
        link=Linker.LD,
        run_env=RunEnv.DOCKER_NATIVE,
    )
    symbols = {
        "main_loop": Symbol(
            name="main_loop", kind=SymbolKind.FUNC, module="src/main.asm", calls=["add_one", "sys_exit"]
        ),
        "add_one": Symbol(name="add_one", kind=SymbolKind.FUNC, module="src/math.asm"),
        "counter": Symbol(name="counter", kind=SymbolKind.DATA, module="src/math.asm"),
        "hidden": Symbol(
            name="hidden", kind=SymbolKind.FUNC, module="src/math.asm", visibility=Visibility.LOCAL
        ),
        "sys_exit": Symbol(
            name="sys_exit", kind=SymbolKind.FUNC, module="src/os.asm", visibility=Visibility.EXTERN
        ),
    }
    structs = {
        "Point": StructDef(
            fields=[StructField(name="x", type="u64", off=0), StructField(name="y", type="u64", off=8)],
            size=16,
        )
    }
    return ContractRegistry(
        version=1, target=target, symbols=symbols, structs=structs, consts={"BUF_SIZE": 4096}
    )


@pytest.mark.parametrize(
    ("dialect", "folder"), [(Dialect.NASM, "nasm"), (Dialect.GAS_INTEL, "gas"), (Dialect.GAS_ATT, "gas")]
)
@pytest.mark.parametrize("stem", ["main", "math"])
def test_rendered_module_matches_golden(dialect: Dialect, folder: str, stem: str) -> None:
    golden = (_GOLDEN / folder / f"{stem}.inc").read_text(encoding="utf-8")
    assert render_module_inc(_registry(dialect), stem) == golden


def test_module_never_imports_what_it_defines() -> None:
    text = render_module_inc(_registry(), "math")
    assert "extern add_one" not in text
    assert "global add_one" in text


def test_hash_header_covers_the_body() -> None:
    header, _, body = render_module_inc(_registry(), "main").partition("\n")
    assert header.endswith(hashlib.sha256(body.encode()).hexdigest())


def test_unsupported_dialect_is_refused() -> None:
    with pytest.raises(CodegenError, match="fasm"):
        render_module_inc(_registry(Dialect.FASM), "main")


def test_stem_collision_is_refused() -> None:
    registry = _registry()
    registry.symbols["dup"] = Symbol(name="dup", kind=SymbolKind.FUNC, module="lib/math.asm")
    with pytest.raises(CodegenError, match="share the file stem"):
        render_all(registry)


def _write_all(workspace: Path, registry: ContractRegistry) -> None:
    for path, text in render_all(registry).items():
        target = workspace / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")


def test_untouched_gen_passes(tmp_path: Path) -> None:
    _write_all(tmp_path, _registry())
    assert check_generated(_registry(), tmp_path) == []
    assert tamper_result(_registry(), tmp_path).status == "pass"


def test_edited_file_is_flagged(tmp_path: Path) -> None:
    _write_all(tmp_path, _registry())
    target = tmp_path / "gen" / "math.inc"
    target.write_text(target.read_text(encoding="utf-8") + "global evil\n", encoding="utf-8", newline="\n")
    codes = [d.code for d in check_generated(_registry(), tmp_path)]
    assert codes == ["tamper.edited"]


def test_missing_file_is_flagged(tmp_path: Path) -> None:
    _write_all(tmp_path, _registry())
    (tmp_path / "gen" / "os.inc").unlink()
    assert [d.code for d in check_generated(_registry(), tmp_path)] == ["tamper.missing"]


def test_extra_file_is_flagged(tmp_path: Path) -> None:
    _write_all(tmp_path, _registry())
    (tmp_path / "gen" / "stubs").mkdir()
    (tmp_path / "gen" / "stubs" / "hack.asm").write_text("; x\n", encoding="utf-8", newline="\n")
    result = tamper_result(_registry(), tmp_path)
    assert result.status == "fail"
    assert [d.code for d in result.diagnostics] == ["tamper.extra"]


def test_absent_gen_dir_fails(tmp_path: Path) -> None:
    result = tamper_result(_registry(), tmp_path)
    assert {d.code for d in result.diagnostics} == {"tamper.missing"}


def test_symlink_in_gen_is_flagged_even_if_target_matches(tmp_path: Path) -> None:
    registry = _registry()
    _write_all(tmp_path, registry)
    real = tmp_path / "elsewhere.inc"
    real.write_text(render_all(registry)["gen/os.inc"], encoding="utf-8", newline="\n")
    link = tmp_path / "gen" / "os.inc"
    link.unlink()
    link.symlink_to(real)
    assert [d.code for d in check_generated(registry, tmp_path)] == ["tamper.edited"]
