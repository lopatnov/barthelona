"""Command-line interface (Typer). Commands land with their phase (docs/roadmap.md)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console

import barthelona
from barthelona.cli._report import report, report_json
from barthelona.cli.bench import bench_app
from barthelona.domain import DOCUMENTS, LevelResult, Verdict
from barthelona.domain.enums import Dialect, Level, ObjFormat
from barthelona.toolchains.dialect import DialectAdapter
from barthelona.training import DatasetError, DatasetReader, TrainingDataSettings, count_verdicts

if TYPE_CHECKING:
    from barthelona.domain.contracts import ContractRegistry
    from barthelona.domain.verification import TestCase
    from barthelona.executors import AgentExecutor
    from barthelona.toolchains import ToolchainLock

app = typer.Typer(
    name="barthelona",
    help="Create or edit multi-file assembly projects from a natural-language request.",
    no_args_is_help=True,
    add_completion=False,
)
training_app = typer.Typer(help="The local training dataset (opt-in, D-036).", no_args_is_help=True)
app.add_typer(training_app, name="training")
app.add_typer(bench_app, name="bench")
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


TransportOption = Annotated[
    str,
    typer.Option(
        "--transport", help="How to reach the agent: auto, wsl (Windows) or local (Linux with Docker)."
    ),
]


def _make_executor(transport: str, command: str) -> AgentExecutor:
    """Build the toolchain executor for *transport*; exit with code 2 when it is unavailable."""
    from barthelona.executors import AgentExecutor, LocalTransport, WslTransport, WslUnavailableError

    kind = transport
    if transport == "auto":
        kind = "wsl" if sys.platform == "win32" else "local"
    try:
        if kind == "wsl":
            return AgentExecutor(WslTransport())
        if kind == "local":
            return AgentExecutor(LocalTransport())
    except WslUnavailableError as exc:
        _err.print(f"[bold red]{command} unavailable:[/bold red] {exc}")
        raise typer.Exit(2) from exc
    raise typer.BadParameter(f"unknown transport {transport!r}; choose auto, wsl or local")


async def _probe(executor: AgentExecutor) -> ToolchainLock:
    from barthelona.toolchains import run_probe

    try:
        return await run_probe(executor)
    finally:
        await executor.aclose()


async def _verify(executor: AgentExecutor, **ladder_args: Any) -> list[LevelResult]:
    from barthelona.verification import LadderOptions, run_ladder

    options: LadderOptions = ladder_args.pop("options")
    options.sandbox = executor.sandbox()
    try:
        return await run_ladder(executor=executor, options=options, **ladder_args)
    finally:
        await executor.aclose()


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
    transport: TransportOption = "auto",
) -> None:
    """Probe the bart-tc container and write config/toolchains.lock.json.

    Needs a running bart-tc Docker container, reached through WSL on Windows
    or directly on a Linux host with Docker.
    """
    from barthelona.toolchains import write_lock_file

    executor = _make_executor(transport, "probe")

    _out.print("Probing bart-tc container…")
    try:
        lock = asyncio.run(_probe(executor))
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


def _load_contracts(path: Path | None) -> ContractRegistry | None:
    if path is None:
        return None
    from barthelona.contracts import ContractsError, load_registry

    try:
        return load_registry(path)
    except ContractsError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _tamper_gate(
    registry: ContractRegistry | None, workspace: Path, tests: list[TestCase]
) -> LevelResult | None:
    """Check ``gen/`` against the registry; a failure stops verify before any tool runs."""
    if registry is None:
        return None
    from barthelona.contracts import CodegenError, tamper_result

    try:
        return tamper_result(registry, workspace, tests)
    except CodegenError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _load_tests(path: Path | None) -> list[TestCase]:
    if path is None:
        return []
    from barthelona.contracts import ContractsError, load_test_cases

    try:
        return load_test_cases(path)
    except ContractsError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def verify(
    workspace: Annotated[Path, typer.Argument(help="Directory containing source files.")],
    level: Annotated[
        str,
        typer.Option(
            "--level",
            "-l",
            help="Highest ladder level to run; levels without a check are reported as unsupported.",
        ),
    ] = "V2",
    dialect: Annotated[
        str | None,
        typer.Option("--dialect", "-d", help="Assembler dialect: nasm, gas-intel, gas-att."),
    ] = None,
    run_id: Annotated[
        str,
        typer.Option(
            "--run-id", help="Session name; staged files live under the cache root's runs/<run-id>/0."
        ),
    ] = "verify",
    contracts: Annotated[
        Path | None,
        typer.Option("--contracts", "-c", help="contracts.yaml; V1 then checks each object's nm symbols."),
    ] = None,
    tests: Annotated[
        Path | None,
        typer.Option(
            "--tests", "-t", help="YAML list of test cases; V6 runs the io_golden ones in bart-run."
        ),
    ] = None,
    transport: TransportOption = "auto",
    json_output: Annotated[
        bool,
        typer.Option(
            "--json", help="Print one JSON document (status and levels) on stdout; progress goes to stderr."
        ),
    ] = False,
) -> None:
    """Run the verification ladder on the assembly sources in WORKSPACE (V0-V2, V6).

    Needs a running bart-tc Docker container, reached through WSL on Windows
    or directly on a Linux host with Docker.

    With --contracts, V1 also compares each object's nm symbols with the
    registry (architecture §13.1).
    Pass --dialect explicitly for Intel-syntax GAS files (gas-intel).
    """
    if not workspace.is_dir():
        raise typer.BadParameter(f"{workspace} is not a directory")

    try:
        up_to = Level(level)
    except ValueError:
        raise typer.BadParameter(f"unknown level {level!r}; choose one of {', '.join(Level)}") from None

    resolved_dialect = dialect or _detect_dialect(workspace)
    adapter = _make_adapter(resolved_dialect)
    ext = _DIALECT_EXTENSION.get(resolved_dialect, ".asm")
    source_files = sorted(workspace.glob(f"*{ext}"))
    if not source_files:
        raise typer.BadParameter(f"no {ext} files found in {workspace}")

    registry = _load_contracts(contracts)
    test_cases = _load_tests(tests)
    gate = _tamper_gate(registry, workspace, test_cases)
    emit = report_json if json_output else report
    if gate is not None and gate.status == "fail":
        raise typer.Exit(emit([gate]))
    executor = _make_executor(transport, "verify")

    from barthelona.verification import LadderOptions

    _err.print(f"Verifying {len(source_files)} file(s) up to {up_to} ({resolved_dialect}) …")
    try:
        results = asyncio.run(
            _verify(
                executor,
                up_to=up_to,
                adapter=adapter,
                source_files=source_files,
                run_id=run_id,
                options=LadderOptions(obj_format=ObjFormat.ELF64, contracts=registry, tests=test_cases),
            )
        )
    except Exception as exc:
        _err.print(f"[bold red]verify failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    raise typer.Exit(emit([*([gate] if gate else []), *results]))


def main() -> None:
    app()
