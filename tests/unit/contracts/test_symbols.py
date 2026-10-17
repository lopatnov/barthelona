"""Tests for the contract registry loader and the V1 ``nm`` symbol check."""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.contracts import (
    ContractsError,
    check_object_symbols,
    load_registry,
    load_test_cases,
    parse_nm,
)
from barthelona.domain.contracts import ContractRegistry, Symbol, SymbolKind, Visibility
from barthelona.domain.enums import ABI, OS, Arch, Dialect, Linker, ObjFormat, RunEnv
from barthelona.domain.project import TargetProfile

_NM_FIXTURE = Path(__file__).parents[2] / "fixtures" / "diagnostics" / "nm" / "2.42" / "module.nm-P-g.txt"


def _target() -> TargetProfile:
    return TargetProfile(
        preset="linux-x64-nasm-static",
        dialect=Dialect.NASM,
        arch=Arch.X86_64,
        os=OS.LINUX,
        abi=ABI.SYSV64,
        obj_format=ObjFormat.ELF64,
        link=Linker.LD,
        run_env=RunEnv.DOCKER_NATIVE,
    )


def _registry(**extra: Symbol) -> ContractRegistry:
    symbols = {
        "add_one": Symbol(name="add_one", kind=SymbolKind.FUNC, module="src/module.asm", calls=["helper"]),
        "counter": Symbol(name="counter", kind=SymbolKind.DATA, module="src/module.asm"),
        "helper": Symbol(name="helper", kind=SymbolKind.FUNC, module="src/helper.asm"),
        **extra,
    }
    return ContractRegistry(version=1, target=_target(), symbols=symbols)


class TestParseNm:
    def test_real_nm_output(self) -> None:
        found = parse_nm(_NM_FIXTURE.read_bytes())
        assert found.defined == {"add_one", "counter"}
        assert found.undefined == {"helper"}

    def test_malformed_lines_are_ignored(self) -> None:
        found = parse_nm(b"\nnonsense\nfoo TT 0\nbar T 0 1\n")
        assert found.defined == {"bar"}

    def test_weak_undefined_counts_as_undefined(self) -> None:
        assert parse_nm(b"ext w\n").undefined == {"ext"}


class TestCheckObjectSymbols:
    def test_matching_object_is_clean(self) -> None:
        found = parse_nm(_NM_FIXTURE.read_bytes())
        assert check_object_symbols(_registry(), "module.asm", found) == []

    def test_unregistered_export_is_fatal(self) -> None:
        found = parse_nm(_NM_FIXTURE.read_bytes() + b"extra T 1\n")
        messages = [d.message for d in check_object_symbols(_registry(), "module.asm", found)]
        assert any("'extra'" in m and "not in the registry" in m for m in messages)

    def test_missing_export_is_fatal(self) -> None:
        found = parse_nm(b"add_one T 0\nhelper U\n")
        diagnostics = check_object_symbols(_registry(), "module.asm", found)
        assert [d.symbol for d in diagnostics] == ["counter"]

    def test_undeclared_import_is_fatal(self) -> None:
        found = parse_nm(_NM_FIXTURE.read_bytes() + b"secret U\n")
        diagnostics = check_object_symbols(_registry(), "module.asm", found)
        assert [d.symbol for d in diagnostics] == ["secret"]

    def test_allow_listed_symbol_is_accepted(self) -> None:
        found = parse_nm(_NM_FIXTURE.read_bytes() + b"_GLOBAL_OFFSET_TABLE_ U\n")
        assert check_object_symbols(_registry(), "module.asm", found) == []

    def test_extern_visibility_declares_an_import(self) -> None:
        ext = Symbol(name="libc_puts", kind=SymbolKind.FUNC, module="lib.asm", visibility=Visibility.EXTERN)
        found = parse_nm(_NM_FIXTURE.read_bytes() + b"libc_puts U\n")
        assert check_object_symbols(_registry(libc_puts=ext), "module.asm", found) == []


class TestLoadRegistry:
    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "contracts.yaml"
        path.write_text(_registry().model_dump_json(), encoding="utf-8")  # JSON is valid YAML
        assert set(load_registry(path).symbols) == {"add_one", "counter", "helper"}

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ContractsError, match="cannot read"):
            load_registry(tmp_path / "nope.yaml")

    def test_not_a_mapping(self, tmp_path: Path) -> None:
        path = tmp_path / "contracts.yaml"
        path.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(ContractsError, match="mapping"):
            load_registry(path)

    def test_schema_violation(self, tmp_path: Path) -> None:
        path = tmp_path / "contracts.yaml"
        path.write_text("version: 0\n", encoding="utf-8")
        with pytest.raises(ContractsError, match=r"contracts\.yaml"):
            load_registry(path)


class TestLoadTestCases:
    def test_golden_case_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "tests.yaml"
        path.write_text(
            "- id: g1\n  kind: io_golden\n  level: V6\n  origin: user\n"
            "  inputs: {stdin: hi}\n  expect: {stdout: hi, exit_code: 0}\n",
            encoding="utf-8",
        )
        (case,) = load_test_cases(path)
        assert (case.id, case.expect.stdout) == ("g1", "hi")

    def test_top_level_must_be_a_list(self, tmp_path: Path) -> None:
        path = tmp_path / "tests.yaml"
        path.write_text("id: g1\n", encoding="utf-8")
        with pytest.raises(ContractsError, match="list of test cases"):
            load_test_cases(path)

    def test_invalid_case_is_reported_with_the_path(self, tmp_path: Path) -> None:
        path = tmp_path / "tests.yaml"
        path.write_text("- id: g1\n", encoding="utf-8")
        with pytest.raises(ContractsError, match=r"tests\.yaml"):
            load_test_cases(path)
