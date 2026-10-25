"""Codegen golden files and the tamper gate (architecture §15.1, invariants 3 and 4)."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from barthelona.contracts import CodegenError, check_generated, render_all, render_module_inc, tamper_result
from barthelona.contracts.cgen import c_type, render_contracts_h, render_harness
from barthelona.contracts.stubs import render_stub
from barthelona.domain.contracts import (
    ContractRegistry,
    RegisterContract,
    StructDef,
    StructField,
    Symbol,
    SymbolKind,
    Visibility,
)
from barthelona.domain.enums import ABI, OS, Arch, Dialect, Level, Linker, ObjFormat, RunEnv
from barthelona.domain.project import TargetProfile
from barthelona.domain.verification import Expectation, TestCase, TestKind, TestOrigin

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
        "add_one": Symbol(
            name="add_one",
            kind=SymbolKind.FUNC,
            module="src/math.asm",
            inputs=[RegisterContract(reg="rdi", type="u64")],
            outputs=[RegisterContract(reg="rax", type="u64")],
        ),
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


@pytest.mark.parametrize(
    ("dialect", "folder", "extension"), [(Dialect.NASM, "nasm", ".asm"), (Dialect.GAS_INTEL, "gas", ".s")]
)
@pytest.mark.parametrize("stem", ["main", "math"])
def test_rendered_stub_matches_golden(dialect: Dialect, folder: str, extension: str, stem: str) -> None:
    golden = (_GOLDEN / folder / "stubs" / f"{stem}{extension}").read_text(encoding="utf-8")
    assert render_stub(_registry(dialect), stem) == golden


def test_a_module_without_functions_has_no_stub() -> None:
    assert render_stub(_registry(), "os") is None


def test_att_stubs_do_not_switch_to_intel_syntax() -> None:
    stub = render_stub(_registry(Dialect.GAS_ATT), "math")
    assert stub is not None
    assert ".intel_syntax" not in stub


def test_stubs_export_functions_only_and_trap() -> None:
    stub = render_stub(_registry(), "math")
    assert stub is not None
    assert "global counter" not in stub
    assert "global hidden" not in stub
    assert "ud2" in stub


def test_render_all_places_stubs_under_gen_stubs() -> None:
    files = render_all(_registry())
    assert {path for path in files if path.startswith("gen/stubs/")} == {
        "gen/stubs/main.asm",
        "gen/stubs/math.asm",
    }


def test_module_never_imports_what_it_defines() -> None:
    text = render_module_inc(_registry(), "math")
    assert "extern add_one" not in text
    assert "global add_one" in text


def test_hash_header_covers_the_body() -> None:
    header, _, body = render_module_inc(_registry(), "main").partition("\n")
    assert header.endswith(hashlib.sha256(body.encode()).hexdigest())


def test_unsupported_dialect_is_refused() -> None:
    registry = _registry(Dialect.FASM)
    with pytest.raises(CodegenError, match="fasm"):
        render_module_inc(registry, "main")


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
    (tmp_path / "gen" / "stubs").mkdir(exist_ok=True)
    (tmp_path / "gen" / "stubs" / "hack.asm").write_text("; x\n", encoding="utf-8", newline="\n")
    result = tamper_result(_registry(), tmp_path)
    assert result.status == "fail"
    assert [d.code for d in result.diagnostics] == ["tamper.extra"]


def test_absent_gen_dir_fails(tmp_path: Path) -> None:
    result = tamper_result(_registry(), tmp_path)
    assert {d.code for d in result.diagnostics} == {"tamper.missing"}


def test_symlink_in_gen_is_flagged_even_if_target_matches(tmp_path: Path) -> None:
    # Windows requires admin privileges for symlinks; skip if not available
    if sys.platform == "win32":
        import pytest

        pytest.skip("symlink creation requires admin on Windows")
    registry = _registry()
    _write_all(tmp_path, registry)
    real = tmp_path / "elsewhere.inc"
    real.write_text(render_all(registry)["gen/os.inc"], encoding="utf-8", newline="\n")
    link = tmp_path / "gen" / "os.inc"
    link.unlink()
    link.symlink_to(real)
    assert [d.code for d in check_generated(registry, tmp_path)] == ["tamper.edited"]


def _harness_case(**overrides: object) -> TestCase:
    fields: dict[str, object] = {
        "id": "add_one_basic",
        "kind": TestKind.C_HARNESS,
        "symbol": "add_one",
        "level": Level.V5,
        "inputs": {"rdi": 41},
        "expect": Expectation(ret=42),
        "origin": TestOrigin.USER,
    }
    return TestCase.model_validate(fields | overrides)


def test_contracts_h_matches_golden() -> None:
    golden = (_GOLDEN / "c" / "contracts.h").read_text(encoding="utf-8")
    assert render_contracts_h(_registry()) == golden


def test_harness_matches_golden() -> None:
    golden = (_GOLDEN / "c" / "add_one_basic.c").read_text(encoding="utf-8")
    assert render_harness(_registry(), _harness_case()) == golden


def test_render_all_includes_header_and_harness() -> None:
    files = render_all(_registry(), [_harness_case()])
    assert "gen/contracts.h" in files
    assert "gen/harness/add_one_basic.c" in files


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"symbol": "nope"}, "not in the registry"),
        ({"expect": Expectation()}, "needs expect.ret"),
        ({"inputs": {}}, "input rdi"),
        ({"inputs": {"rdi": "x"}}, "must be an integer"),
        ({"expect": Expectation(ret=1, stdout="x")}, "checks only expect.ret"),
        ({"inputs": {"rdi": 1, "rsi": 2}}, "not inputs of add_one"),
        ({"inputs": {"rdi": -1}}, "does not fit u64"),
        ({"expect": Expectation(ret=2**64)}, "does not fit u64"),
    ],
)
def test_bad_harness_case_is_refused(overrides: dict[str, object], message: str) -> None:
    registry = _registry()
    case = _harness_case(**overrides)
    with pytest.raises(CodegenError, match=message):
        render_harness(registry, case)


@pytest.mark.parametrize(
    ("type_name", "expected"),
    [("u64", "uint64_t"), ("char*", "char *"), ("u8 **", "uint8_t **"), ("void", "void")],
)
def test_c_type(type_name: str, expected: str) -> None:
    assert c_type(type_name) == expected


def test_c_type_rejects_unknown() -> None:
    with pytest.raises(CodegenError, match="no C type"):
        c_type("mystery")


def test_tamper_covers_harness_files(tmp_path: Path) -> None:
    registry, tests = _registry(), [_harness_case()]
    for path, text in render_all(registry, tests).items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8", newline="\n")
    assert check_generated(registry, tmp_path, tests) == []
    assert [d.code for d in check_generated(registry, tmp_path)] == ["tamper.extra"]


@pytest.mark.skipif(shutil.which("gcc") is None, reason="needs gcc in PATH")
def test_generated_c_compiles_and_runs(tmp_path: Path) -> None:
    for path, text in render_all(_registry(), [_harness_case()]).items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8", newline="\n")
    (tmp_path / "impl.c").write_text(
        '#include "gen/contracts.h"\nuint64_t add_one(uint64_t rdi) { return rdi + 1; }\n',
        encoding="utf-8",
        newline="\n",
    )
    exe = tmp_path / "t"
    build = ["gcc", "-Wall", "-Werror", "-o", str(exe), "impl.c", "gen/harness/add_one_basic.c"]
    subprocess.run(build, cwd=tmp_path, check=True)
    assert subprocess.run([str(exe)], check=False).returncode == 0


def test_custom_abi_function_has_no_prototype_and_no_harness() -> None:
    registry = _registry()
    registry.symbols["add_one"] = registry.symbols["add_one"].model_copy(update={"abi": "custom"})
    assert "// add_one: no prototype" in render_contracts_h(registry)
    case = _harness_case()
    with pytest.raises(CodegenError, match="custom ABI"):
        render_harness(registry, case)


def test_duplicate_harness_ids_are_refused() -> None:
    registry = _registry()
    cases = [_harness_case(), _harness_case(id="ADD_ONE_BASIC")]
    with pytest.raises(CodegenError, match="unique"):
        render_all(registry, cases)


def _with_symbol(**update: object) -> ContractRegistry:
    registry = _registry()
    registry.symbols["add_one"] = registry.symbols["add_one"].model_copy(update=update)
    return registry


_U64 = RegisterContract(reg="rax", type="u64")


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"inputs": [RegisterContract(reg="rsi", type="u64")]}, "not in rdi"),
        ({"inputs": [RegisterContract(reg="xmm0", type="u64")]}, "not in rdi"),
        ({"inputs": [RegisterContract(reg="rdi", type="char*")]}, "non-integer"),
        ({"outputs": []}, "exactly one value in rax"),
        ({"outputs": [RegisterContract(reg="rdx", type="u64")]}, "exactly one value in rax"),
        ({"outputs": [_U64, RegisterContract(reg="rdx", type="u64")]}, "exactly one value"),
        ({"flags_out": {"CF": "carry"}}, "flags cannot be observed"),
    ],
)
def test_harness_refuses_contracts_c_cannot_reproduce(update: dict[str, object], message: str) -> None:
    registry = _with_symbol(**update)
    inputs = {item.reg: 1 for item in registry.symbols["add_one"].inputs}
    case = _harness_case(inputs=inputs)
    with pytest.raises(CodegenError, match=message):
        render_harness(registry, case)


def test_win64_uses_its_own_argument_registers() -> None:
    registry = _with_symbol(inputs=[RegisterContract(reg="ecx", type="u32")])
    registry = registry.model_copy(update={"target": registry.target.model_copy(update={"abi": ABI.WIN64})})
    case = _harness_case(inputs={"ecx": 41})
    assert "add_one(41ULL)" in render_harness(registry, case)
    sysv_style = _registry().model_copy(update={"target": registry.target})
    case = _harness_case()
    with pytest.raises(CodegenError, match="not in rcx"):
        render_harness(sysv_style, case)


def test_large_constants_do_not_use_enum() -> None:
    registry = _registry().model_copy(update={"consts": {"BIG": 2**32, "HUGE": 2**63}})
    text = render_contracts_h(registry)
    assert "#define BIG 4294967296LL" in text
    assert f"#define HUGE {2**63}ULL" in text
