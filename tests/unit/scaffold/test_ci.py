"""CI/CD templates render for the supported families and fail loudly for the rest (D-048)."""

import re
from typing import Any

import pytest
from ruamel.yaml import YAML

from barthelona.domain.enums import ABI, OS, Arch, Dialect, Linker, ObjFormat, RunEnv
from barthelona.domain.project import ModuleSpec, ProjectSpec, TargetProfile
from barthelona.scaffold import LINUX_X64, UnsupportedCiTarget, ci_family, render_ci

REF = "d76afc5ed3f5611bff1f7594035a1fbc4ac65686"
USES = re.compile(r"uses: (?P<action>[\w./-]+)@(?P<ref>\S+)")
MODULES = ["src/main.asm", "src/game.asm"]


def _target(dialect: Dialect = Dialect.NASM, **changes: Any) -> TargetProfile:
    fields: dict[str, Any] = {
        "preset": "linux-x64-test",
        "dialect": dialect,
        "arch": Arch.X86_64,
        "os": OS.LINUX,
        "abi": ABI.SYSV64,
        "obj_format": ObjFormat.ELF64,
        "link": Linker.LD,
        "run_env": RunEnv.DOCKER_NATIVE,
    }
    return TargetProfile.model_validate(fields | changes)


def _project(target: TargetProfile, paths: list[str] = MODULES) -> ProjectSpec:
    return ProjectSpec(
        id="p1",
        slug="snake",
        request_original="a snake game",
        request_lang="en",
        summary_en="Snake",
        target=target,
        modules=[ModuleSpec(path=p, purpose="module") for p in paths],
    )


def _parse(text: str) -> Any:
    return YAML(typ="safe").load(text)


@pytest.mark.parametrize("dialect", [Dialect.NASM, Dialect.GAS_INTEL, Dialect.GAS_ATT])
def test_linux_x64_renders_valid_yaml_without_placeholders(dialect: Dialect) -> None:
    files = render_ci(_project(_target(dialect)), REF)

    assert sorted(files) == [
        ".github/dependabot.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
    ]
    for path, text in files.items():
        assert "__" not in text, path
        assert _parse(text), path


def test_ci_workflow_pins_the_verifier_and_requires_the_ladder() -> None:
    ci = render_ci(_project(_target()), REF)[".github/workflows/ci.yml"]

    assert f"BARTHELONA_REF: {REF}" in ci
    assert "verify src --dialect nasm --level V6" in ci
    assert "for level in tamper V0 V1 V2 V5 V6; do" in ci


def test_release_workflow_builds_every_module_in_order() -> None:
    release = render_ci(_project(_target()), REF)[".github/workflows/release.yml"]

    assert "nasm -f elf64 -o build/main.o src/main.asm" in release
    assert "nasm -f elf64 -o build/game.o src/game.asm" in release
    assert "ld -z noexecstack -e _start -o build/snake-linux-x86_64 build/main.o build/game.o" in release
    assert "--generate-notes" in release


def test_gas_release_uses_binutils_as() -> None:
    release = render_ci(_project(_target(Dialect.GAS_INTEL), ["src/a.s"]), REF)[
        ".github/workflows/release.yml"
    ]

    assert "as -o build/a.o src/a.s" in release
    assert "install -y --no-install-recommends binutils" in release


def test_every_action_is_pinned_to_a_commit_sha() -> None:
    for text in render_ci(_project(_target()), REF).values():
        for match in USES.finditer(text):
            assert re.fullmatch(r"[0-9a-f]{40}", match["ref"]), f"{match['action']} is not pinned"


def test_workflows_grant_only_the_permissions_they_use() -> None:
    files = render_ci(_project(_target()), REF)

    assert _parse(files[".github/workflows/ci.yml"])["permissions"] == {"contents": "read"}
    assert _parse(files[".github/workflows/release.yml"])["permissions"] == {
        "actions": "read",
        "contents": "write",
    }


def test_shell_metacharacters_in_module_paths_are_quoted() -> None:
    release = render_ci(_project(_target(), ["src/a b.asm"]), REF)[".github/workflows/release.yml"]

    assert "-o 'build/a b.o' 'src/a b.asm'" in release


def test_family_lookup() -> None:
    assert ci_family(_target()) == LINUX_X64


@pytest.mark.parametrize(
    "changes",
    [
        {"os": OS.WINDOWS},
        {"arch": Arch.AARCH64},
        {"link": Linker.LIBC},
        {"dialect": Dialect.FASM},
    ],
)
def test_other_targets_have_no_template_yet(changes: dict[str, Any]) -> None:
    with pytest.raises(UnsupportedCiTarget, match="no CI/CD template"):
        render_ci(_project(_target(**changes)), REF)


@pytest.mark.parametrize(
    ("ref", "paths", "message"),
    [
        ("main", MODULES, "full commit sha"),
        (REF, [], "no modules"),
        (REF, ["src/a.asm", "lib/b.asm"], "one source directory"),
        (REF, ["src/a.asm", "src/a.s"], "unique"),
        (REF, ["src/${{ github.token }}.asm"], "GitHub expression"),
    ],
)
def test_invalid_projects_are_rejected(ref: str, paths: list[str], message: str) -> None:
    with pytest.raises(UnsupportedCiTarget, match=message):
        render_ci(_project(_target(), paths), ref)
