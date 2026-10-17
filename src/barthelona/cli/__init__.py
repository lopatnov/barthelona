"""Command-line interface (Typer). Commands land with their phase (docs/roadmap.md)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

import barthelona
from barthelona.domain import DOCUMENTS, LevelResult, Verdict
from barthelona.domain.enums import Dialect, Level, ObjFormat
from barthelona.toolchains.dialect import DialectAdapter
from barthelona.training import DatasetError, DatasetReader, TrainingDataSettings, count_verdicts

app = typer.Typer(
    name="barthelona",
    help="Create or edit multi-file assembly projects from a natural-language request.",
    no_args_is_help=True,
    add_completion=False,
)
training_app = typer.Typer(help="The local training dataset (opt-in, D-036).", no_args_is_help=True)
app.add_typer(training_app, name="training")
_out = Console(soft_wrap=True, highlight=False)
_err = Console(stderr=True, soft_wrap=True, highlight=False)


@app.command()
def version() -> None:
    """Print the barthelona version."""
    _out.print(barthelona.__version__)


@app.command()
def schema(
    model: Annotated[str | None, typer.Argument(help="Document name, e.g. TopologyRequest.")] = None,
) -> None:
    """Print the JSON schema of a domain document, or list the documents."""
    if model is None:
        for name in sorted(DOCUMENTS):
            _out.print(name)
        return
    cls = DOCUMENTS.get(model)
    if cls is None:
        raise typer.BadParameter(f"unknown document {model!r}; run without an argument to list them")
    _out.print(json.dumps(cls.model_json_schema(), indent=2, sort_keys=True), markup=False)


@app.command()
def probe(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Where to write the lock file (default: config/toolchains.lock.json).",
        ),
    ] = Path("config/toolchains.lock.json"),
) -> None:
    """Probe the bart-tc container and write config/toolchains.lock.json.

    Requires Windows with WSL and a running bart-tc Docker container.
    """
    from barthelona.executors import WslUnavailableError
    from barthelona.executors.wsl import WslExecutor
    from barthelona.toolchains import run_probe, write_lock_file

    try:
        executor = WslExecutor()
    except WslUnavailableError as exc:
        _err.print(f"[bold red]probe unavailable:[/bold red] {exc}")
        raise typer.Exit(2) from exc

    _out.print("Probing bart-tc container…")
    try:
        with executor:
            lock = run_probe(executor)
    except Exception as exc:  # surface all probe errors to the user as a single message
        _err.print(f"[bold red]probe failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    write_lock_file(lock, output)
    _out.print(f"Wrote {output}")
    _out.print(f"  toolchain image: {lock.toolchain_image_digest or '(unknown)'}")
    _out.print(f"  runner image:    {lock.runner_image_digest or '(unknown)'}")
    for name, info in lock.tools.items():
        _out.print(f"  {name}: {info.version} at {info.path}")


@training_app.command("status")
def training_status() -> None:
    """Show whether training data is collected, where, and how many samples each verdict has."""
    settings = TrainingDataSettings()
    state = "enabled" if settings.enabled else "disabled (set BARTHELONA_TRAINING_DATA_ENABLED=1)"
    _out.print(f"collection: {state}", markup=False)
    _out.print(f"directory: {settings.directory}", markup=False)
    try:
        verdicts = count_verdicts(DatasetReader(settings.directory).samples())
    except DatasetError as error:
        _err.print(str(error), markup=False)
        raise typer.Exit(1) from error
    for verdict in Verdict:
        _out.print(f"{verdict.value}: {verdicts[verdict]}", markup=False)


_DIALECT_EXTENSION: dict[str, str] = {
    Dialect.NASM: ".asm",
    Dialect.GAS_INTEL: ".s",
    Dialect.GAS_ATT: ".s",
}


def _make_adapter(dialect: str) -> DialectAdapter:
    from barthelona.toolchains import GasAttAdapter, GasIntelAdapter, NasmAdapter

    if dialect == Dialect.NASM:
        return NasmAdapter()
    if dialect == Dialect.GAS_INTEL:
        return GasIntelAdapter()
    if dialect == Dialect.GAS_ATT:
        return GasAttAdapter()
    raise typer.BadParameter(f"unsupported dialect {dialect!r}; choose: nasm, gas-intel, gas-att")


def _detect_dialect(workspace: Path) -> str:
    """Infer the dialect from the dominant source extension in *workspace*."""
    asm_count = len(list(workspace.glob("*.asm")))
    s_count = len(list(workspace.glob("*.s")))
    if asm_count >= s_count and asm_count > 0:
        return Dialect.NASM
    if s_count > 0:
        return Dialect.GAS_ATT
    raise typer.BadParameter(f"no .asm or .s files found in {workspace}; specify --dialect explicitly")


_STATUS_ICON: dict[str, str] = {"pass": "✓", "skipped": "—"}


def _report(results: list[LevelResult]) -> int:
    """Print each ladder level and its diagnostics; return the process exit code."""
    for r in results:
        _out.print(f"  {_STATUS_ICON.get(r.status, '✗')} {r.level}: {r.status} ({r.secs:.2f}s)")
        for d in r.diagnostics:
            loc = f"{d.file}:{d.line}" if d.file and d.line else (d.file or "")
            _out.print(f"    {d.severity} [{d.level}] {loc} {d.message}", markup=False)
    return 1 if any(r.status == "fail" for r in results) else 0


@app.command()
def verify(
    workspace: Annotated[Path, typer.Argument(help="Directory containing source files.")],
    level: Annotated[
        str,
        typer.Option("--level", "-l", help="Highest ladder level to run (V0, V1, V2)."),
    ] = "V2",
    dialect: Annotated[
        str | None,
        typer.Option("--dialect", "-d", help="Assembler dialect: nasm, gas-intel, gas-att."),
    ] = None,
    work_dir: Annotated[
        str,
        typer.Option("--work-dir", help="WSL path for staged files."),
    ] = "~/.cache/barthelona/verify-tmp",
) -> None:
    """Run the verification ladder (V0-V2) on the assembly sources in WORKSPACE.

    Requires Windows with WSL and a running bart-tc Docker container.

    Phase 0 note: V1 only assembles; the nm/registry symbol check
    (architecture §13.1) is deferred until contracts.yaml is populated.
    Pass --dialect explicitly for Intel-syntax GAS files (gas-intel).
    """
    from barthelona.executors import WslUnavailableError
    from barthelona.executors.wsl import WslExecutor
    from barthelona.verification import run_ladder

    if not workspace.is_dir():
        raise typer.BadParameter(f"{workspace} is not a directory")

    try:
        up_to = Level(level)
    except ValueError:
        raise typer.BadParameter(f"unknown level {level!r}; choose V0, V1 or V2") from None

    resolved_dialect = dialect or _detect_dialect(workspace)
    adapter = _make_adapter(resolved_dialect)
    ext = _DIALECT_EXTENSION.get(resolved_dialect, ".asm")
    source_files = sorted(workspace.glob(f"*{ext}"))
    if not source_files:
        raise typer.BadParameter(f"no {ext} files found in {workspace}")

    try:
        executor = WslExecutor()
    except WslUnavailableError as exc:
        _err.print(f"[bold red]verify unavailable:[/bold red] {exc}")
        raise typer.Exit(2) from exc

    _out.print(f"Verifying {len(source_files)} file(s) up to {up_to} ({resolved_dialect}) …")
    try:
        with executor:
            results = run_ladder(
                up_to=up_to,
                executor=executor,
                adapter=adapter,
                source_files=source_files,
                work_dir=work_dir,
                obj_format=ObjFormat.ELF64,
            )
    except Exception as exc:
        _err.print(f"[bold red]verify failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    raise typer.Exit(_report(results))


def main() -> None:
    app()
