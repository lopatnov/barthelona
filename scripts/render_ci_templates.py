"""Render the CI/CD templates for a sample project into a directory, so actionlint can check them (D-048).

Usage: python scripts/render_ci_templates.py <outdir>
"""

from __future__ import annotations

import sys
from pathlib import Path

from barthelona.domain.enums import ABI, OS, Arch, Dialect, Linker, ObjFormat, RunEnv
from barthelona.domain.project import ModuleSpec, ProjectSpec, TargetProfile
from barthelona.scaffold import render_ci

SAMPLE_REF = "0" * 40


def sample_project(dialect: Dialect) -> ProjectSpec:
    target = TargetProfile(
        preset=f"linux-x64-{dialect}",
        dialect=dialect,
        arch=Arch.X86_64,
        os=OS.LINUX,
        abi=ABI.SYSV64,
        obj_format=ObjFormat.ELF64,
        link=Linker.LD,
        run_env=RunEnv.DOCKER_NATIVE,
    )
    return ProjectSpec(
        id="sample",
        slug="sample",
        request_original="sample",
        request_lang="en",
        summary_en="sample",
        target=target,
        modules=[
            ModuleSpec(path="src/main.asm", purpose="entry"),
            ModuleSpec(path="src/util.asm", purpose="helpers"),
        ],
    )


def main(out_dir: Path) -> None:
    for dialect in (Dialect.NASM, Dialect.GAS_INTEL):
        for relative, text in render_ci(sample_project(dialect), SAMPLE_REF).items():
            target = out_dir / str(dialect) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
