"""Bench prompts: Jinja2 templates under ``bench/prompts/`` and the feedback block for fix iterations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from barthelona.bench.task import BenchTask
from barthelona.contracts import render_module_inc
from barthelona.domain.enums import Dialect
from barthelona.domain.verification import LevelResult

_ENV = Environment(undefined=StrictUndefined, keep_trailing_newline=True, autoescape=False)  # noqa: S701  # prompts are plain text
_MAX_DIAGNOSTICS = 10
_MAX_MESSAGE_CHARS = 600


@dataclass(frozen=True)
class PromptSet:
    """Template texts: `single` for the first attempt, `fix` for each retry."""

    single: str
    fix: str


def load_prompts(root: Path) -> PromptSet:
    directory = root / "prompts"
    return PromptSet(
        single=(directory / "single.md.j2").read_text(encoding="utf-8"),
        fix=(directory / "fix.md.j2").read_text(encoding="utf-8"),
    )


def render_feedback(results: Sequence[LevelResult]) -> str:
    """Plain-text oracle output for the model: each failing level with its first diagnostics."""
    blocks: list[str] = []
    for result in results:
        if result.status == "pass":
            continue
        lines = [f"{result.level}: {result.status}"]
        for diagnostic in result.diagnostics[:_MAX_DIAGNOSTICS]:
            where = f" ({diagnostic.file}:{diagnostic.line})" if diagnostic.file and diagnostic.line else ""
            lines.append(f"- [{diagnostic.tool}] {diagnostic.message[:_MAX_MESSAGE_CHARS]}{where}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) or "no level reported a failure, but the definition of done is not met"


def render_first_prompt(prompts: PromptSet, task: BenchTask, source_name: str) -> str:
    include_name = f"gen/{task.module}.inc"
    directive = f'%include "{include_name}"' if task.dialect == Dialect.NASM else f'.include "{include_name}"'
    return _ENV.from_string(prompts.single).render(
        task=task,
        source_name=source_name,
        include_name=include_name,
        include_directive=directive,
        include_text=render_module_inc(task.registry, task.module),
    )


def render_fix_prompt(prompts: PromptSet, task: BenchTask, source_name: str, feedback: str) -> str:
    return _ENV.from_string(prompts.fix).render(task=task, source_name=source_name, feedback=feedback)
