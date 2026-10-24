"""Render the CI/CD files of a produced assembler project from templates (D-048).

Templates live in ``templates/<family>/`` and use ``__NAME__`` placeholders. A family is a
target the project can be built for; targets without one fail with ``UnsupportedCiTarget``
(``StopReason.UNSUPPORTED_TARGET``) instead of getting a workflow that cannot work.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping
from importlib import resources
from pathlib import PurePosixPath

from barthelona.domain.enums import ABI, OS, Arch, Dialect, Linker, ObjFormat
from barthelona.domain.project import ProjectSpec, TargetProfile

LINUX_X64 = "linux-x64"
DEFAULT_REQUIRED_LEVELS = ("tamper", "V0", "V1", "V2", "V5", "V6")
DEFAULT_CONTRACTS = "contracts.yaml"
DEFAULT_TESTS = "tests/acceptance.yaml"
WORKFLOWS_DIR = ".github/workflows"

_TEMPLATE_OUTPUTS = {
    "ci.yml": f"{WORKFLOWS_DIR}/ci.yml",
    "release.yml": f"{WORKFLOWS_DIR}/release.yml",
    "dependabot.yml": ".github/dependabot.yml",
}
_LINUX_X64_DIALECTS = {
    Dialect.NASM: ("nasm", "nasm -f elf64 -o {obj} {src}"),
    Dialect.GAS_INTEL: ("binutils", "as -o {obj} {src}"),
    Dialect.GAS_ATT: ("binutils", "as -o {obj} {src}"),
}
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_BLOCK_PLACEHOLDER = re.compile(r"^( *)__([A-Z_]+)__$", re.MULTILINE)
_ANY_PLACEHOLDER = re.compile(r"__[A-Z_]+__")


class UnsupportedCiTarget(ValueError):
    """No CI/CD template family exists for the target (or the project cannot be built by one)."""


def ci_family(target: TargetProfile) -> str:
    """The template family for the target, or raise ``UnsupportedCiTarget`` naming what is missing."""
    native = (target.arch, target.os, target.abi, target.obj_format, target.link) == (
        Arch.X86_64,
        OS.LINUX,
        ABI.SYSV64,
        ObjFormat.ELF64,
        Linker.LD,
    )
    if native and target.dialect in _LINUX_X64_DIALECTS:
        return LINUX_X64
    raise UnsupportedCiTarget(
        f"no CI/CD template for preset {target.preset!r} "
        f"({target.dialect}, {target.arch}, {target.os}, {target.obj_format}, {target.link})"
    )


def render_ci(
    project: ProjectSpec,
    barthelona_ref: str,
    required_levels: tuple[str, ...] = DEFAULT_REQUIRED_LEVELS,
) -> dict[str, str]:
    """Workspace-relative path -> file text for the project's workflows and Dependabot config."""
    family = ci_family(project.target)
    if not _COMMIT_SHA.match(barthelona_ref):
        raise UnsupportedCiTarget(f"barthelona_ref must be a full commit sha, got {barthelona_ref!r}")
    values = _linux_x64_values(project, barthelona_ref, required_levels)
    _reject_expression_injection(values)
    return {out: _render(family, name, values) for name, out in _TEMPLATE_OUTPUTS.items()}


def build_commands(project: ProjectSpec) -> list[str]:
    """The shell lines that assemble and link the project, as the release workflow runs them."""
    ci_family(project.target)
    return _linux_x64_values(project, "0" * 40, ())["BUILD_COMMANDS"].split("\n")


def render_golden_ci(project: ProjectSpec, barthelona_ref: str, source: str, tests: str) -> str:
    """The ``ci.yml`` of a single-module project: assemble it and run its golden tests in the emulator."""
    ci_family(project.target)
    if project.target.dialect is not Dialect.NASM:
        raise UnsupportedCiTarget(f"the golden CI runs NASM sources only, not {project.target.dialect}")
    if not _COMMIT_SHA.match(barthelona_ref):
        raise UnsupportedCiTarget(f"barthelona_ref must be a full commit sha, got {barthelona_ref!r}")
    values = {
        "SLUG": project.slug,
        "BARTHELONA_REF": barthelona_ref,
        "SOURCE": shlex.quote(source),
        "TESTS": shlex.quote(tests),
    }
    _reject_expression_injection(values)
    return _render(LINUX_X64, "ci-golden.yml", values)


def _linux_x64_values(project: ProjectSpec, ref: str, required_levels: tuple[str, ...]) -> Mapping[str, str]:
    target = project.target
    modules = [PurePosixPath(m.path) for m in project.modules]
    if not modules:
        raise UnsupportedCiTarget("the project has no modules to build")
    source_dir = _single_source_dir(modules)
    package, assemble = _LINUX_X64_DIALECTS[target.dialect]
    objects = [f"build/{path.stem}.o" for path in modules]
    commands = [
        assemble.format(obj=shlex.quote(obj), src=shlex.quote(str(p)))
        for obj, p in zip(objects, modules, strict=True)
    ]
    entry = shlex.quote(target.entry or "_start")
    quoted_objects = " ".join(map(shlex.quote, objects))
    link = f"ld -z noexecstack -e {entry} -o build/{project.slug}-linux-x86_64 {quoted_objects}"
    return {
        "SLUG": project.slug,
        "BARTHELONA_REF": ref,
        "SOURCE_DIR": shlex.quote(source_dir),
        "DIALECT": str(target.dialect),
        "CONTRACTS": DEFAULT_CONTRACTS,
        "TESTS": DEFAULT_TESTS,
        "REQUIRED_LEVELS": " ".join(required_levels),
        "ASSEMBLER_PACKAGE": package,
        "ARTIFACT": f"{project.slug}-linux-x86_64",
        "BUILD_COMMANDS": "\n".join([*commands, link]),
    }


def _single_source_dir(modules: list[PurePosixPath]) -> str:
    directories = {str(path.parent) for path in modules}
    if len(directories) != 1:
        raise UnsupportedCiTarget(f"modules must share one source directory, got {sorted(directories)}")
    stems = [path.stem for path in modules]
    if len(set(stems)) != len(stems):
        raise UnsupportedCiTarget(
            "module file names must be unique across the project (object files share build/)"
        )
    return directories.pop()


def _reject_expression_injection(values: Mapping[str, str]) -> None:
    """Actions expands ``${{ }}`` before the shell runs, so shell quoting cannot neutralise it."""
    for key, value in values.items():
        if "${{" in value:
            raise UnsupportedCiTarget(f"{key} contains a GitHub expression: {value!r}")


def _render(family: str, name: str, values: Mapping[str, str]) -> str:
    template = resources.files(__package__).joinpath("templates", family, name).read_text(encoding="utf-8")
    text = _BLOCK_PLACEHOLDER.sub(lambda m: _indent_block(m.group(1), values[m.group(2)]), template)
    for key, value in values.items():
        text = text.replace(f"__{key}__", value)
    leftover = _ANY_PLACEHOLDER.findall(text)
    if leftover:
        raise UnsupportedCiTarget(
            f"template {family}/{name} has unfilled placeholders: {sorted(set(leftover))}"
        )
    return text


def _indent_block(indent: str, value: str) -> str:
    return "\n".join(f"{indent}{line}" for line in value.split("\n"))
