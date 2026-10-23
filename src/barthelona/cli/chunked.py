"""``barthelona chunked``: run one long task through the model gateway as Markovian chunks."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from barthelona.llm import (
    CatalogError,
    ChatMessage,
    CompletionRequest,
    Gateway,
    GatewayError,
    MarkovianConfig,
    MarkovianResult,
    OpenAIChatBackend,
    extract_code,
    load_catalog,
    run_markovian,
)
from barthelona.llm.guard import wrap_untrusted
from barthelona.llm.hmem import HMem, facts_from_state
from barthelona.llm.runlog import RunLog
from barthelona.verification.asm_gate import AssembleResult, assemble_source

chunked_app = typer.Typer(
    help="Long tasks as bounded chunks with flat context (Markovian).", no_args_is_help=True
)
_out = Console(soft_wrap=True, highlight=False)
_err = Console(stderr=True, soft_wrap=True, highlight=False)


def _table(result: MarkovianResult) -> Table:
    table = Table(
        "chunk",
        "served by",
        "answered by",
        "tokens in",
        "tokens out",
        "chunk tokens",
        "ms",
        "marker",
        "carryover",
    )
    for chunk in result.chunks:
        table.add_row(
            str(chunk.index + 1),
            chunk.served_by,
            chunk.answered_by or "-",
            str(chunk.tokens_in),
            str(chunk.tokens_out),
            f"{chunk.tokens} ({chunk.token_source})",
            str(chunk.latency_ms),
            chunk.marker,
            chunk.carryover,
        )
    return table


_PLAN = "Write a short numbered plan (at most 8 steps, under 200 words) for the task. No code."
_REVIEW = (
    "Review this output against the task. List concrete problems (wrong syntax, missing parts, wrong "
    "calling convention) in at most 6 bullet points, or say it looks complete. Advisory only."
)


def _side_call(gateway: Gateway, role: str | None, label: str, instruction: str, material: str) -> str:
    """One bounded call to another role's chain (planner or reviewer); empty when unused or failed."""
    if role is None:
        return ""
    request = CompletionRequest(
        messages=(
            ChatMessage(role="system", content=instruction),
            ChatMessage(role="user", content=material),
        ),
        max_tokens=1500,
    )
    try:
        done = asyncio.run(gateway.complete(role, request))
    except GatewayError as exc:
        _err.print(f"{label} ({role}) skipped: {exc}", markup=False)
        return ""
    _err.print(
        f"{label} ({role}): served_by={done.served_by} tokens_out={done.record.tokens_out} "
        f"ms={done.record.latency_ms}",
        markup=False,
    )
    return done.text.strip()


def _remember(store: HMem, result: MarkovianResult, recalled: int, domain: str, verdict: str) -> None:
    """Keep what the run learned, unless the oracle did not accept its output ("pass" or "" for no oracle)."""
    if verdict not in ("pass", ""):
        _err.print(f"memory: recalled={recalled} written=0 (assemble oracle: {verdict})")
        store.close()
        return
    facts = [fact for chunk in result.chunks for fact in facts_from_state(chunk.state)]
    written = store.ingest(facts, source=f"markovian:run-{int(time.time())}", domain=domain)
    _err.print(f"memory: recalled={recalled} written={written} stored={store.count()}")
    store.close()


def _answer_text(result: MarkovianResult, code: bool, out: Path | None) -> str:
    """The text to deliver; with --code only source blocks, and an answer without any is an error."""
    if not code:
        return result.text
    text = extract_code(result.text)
    if out is not None:  # the unfiltered answer, so a bad extraction can be inspected
        out.with_name(out.name + ".raw.txt").write_text(result.text + "\n", encoding="utf-8", newline="\n")
    if not text.strip():
        _err.print("no code blocks in the answer: nothing written (see the .raw.txt next to --out)")
        raise typer.Exit(1)
    return text


@chunked_app.command("run")
def run(
    task: Annotated[str, typer.Argument(help="The task text, or @file to read it from a file.")],
    profile: Annotated[
        str, typer.Option(help="Catalog profile; 'meterless' routes via Nightshift.")
    ] = "meterless",
    role: Annotated[str, typer.Option(help="Catalog role whose chain answers each chunk.")] = "worker",
    out: Annotated[Path | None, typer.Option(help="Write the assembled output to this file.")] = None,
    code: Annotated[
        bool, typer.Option("--code", help="Write only the fenced code blocks (a source file), not the prose.")
    ] = False,
    memory: Annotated[
        Path | None,
        typer.Option(
            help="H-MEM store (SQLite): recall before chunk 1, write what the run learned at the end."
        ),
    ] = None,
    domain: Annotated[str, typer.Option(help="H-MEM domain used to rank and tag memories.")] = "assembly",
    assemble: Annotated[
        bool,
        typer.Option(
            "--assemble",
            help="Assemble the code with NASM; the run is green only if it assembles (implies --code).",
        ),
    ] = False,
    repair: Annotated[
        int, typer.Option(min=0, max=3, help="With --assemble: extra attempts that get NASM's errors back.")
    ] = 0,
    nasm: Annotated[
        str | None,
        typer.Option(help="nasm binary (default: BARTHELONA_NASM, NASM_PATH, PATH, usual Windows folders)."),
    ] = None,
    stats: Annotated[
        Path | None, typer.Option(help="Run statistics database (SQLite), e.g. var/runs.sqlite.")
    ] = None,
    plan_role: Annotated[
        str | None, typer.Option(help="Role that writes a short plan first (e.g. planner).")
    ] = None,
    review_role: Annotated[
        str | None, typer.Option(help="Role that reviews the output afterwards (e.g. cheap); advisory.")
    ] = None,
    chunk_tokens: Annotated[int, typer.Option(help="Tokens per chunk (engine range 1000-128000).")] = 8000,
    carryover_tokens: Annotated[int, typer.Option(help="Tokens of state carried between chunks.")] = 800,
    max_chunks: Annotated[int, typer.Option(help="Upper bound on chunks (1-32).")] = 24,
    catalog_path: Annotated[Path, typer.Option("--catalog", help="Model catalog.")] = Path(
        "config/models.yaml"
    ),
) -> None:
    """Run TASK in chunks, print per-chunk tokens and latency, and exit non-zero unless it completed."""
    try:
        catalog = load_catalog(catalog_path)
        config = MarkovianConfig(chunk_tokens, carryover_tokens, max_chunks)
    except (CatalogError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    if task.startswith("@"):
        task = Path(task[1:]).read_text(encoding="utf-8")
    code = code or assemble
    gateway = Gateway(catalog, {"openai_chat": OpenAIChatBackend()}, profile=profile)
    store = HMem(memory) if memory is not None else None
    recall = store.query(task, domain=domain) if store else None
    recalled = len(recall.memories) if recall else 0
    memory_context = recall.context if recall else ""
    plan = _side_call(gateway, plan_role, "plan", _PLAN, task)
    chunk_task = f"{task}\n\nPlan from the planner (follow it):\n{plan}" if plan else task

    def attempt(task_text: str, number: int) -> tuple[MarkovianResult, str]:
        result = asyncio.run(run_markovian(gateway, role, task_text, config, memory_context))
        _record_stats(stats, result, task, profile, recalled, number)
        _report(result)
        return result, _answer_text(result, code, out)

    result, text, gate = _until_it_assembles(attempt, chunk_task, nasm if assemble else NO_ORACLE, repair)
    accepted = gate is None or gate.status == "pass"
    if store:
        _remember(store, result, recalled, domain, gate.status if gate else "")
    review = _side_call(gateway, review_role, "review", _REVIEW, f"Task:\n{task}\n\nOutput:\n{text}")
    if review:
        _err.print(f"review (advisory, the oracle decides):\n{review}", markup=False)
    if out is not None:
        out.write_text(text + "\n", encoding="utf-8", newline="\n")
    else:
        _out.print(text, markup=False)
    if gate is not None:
        _err.print(
            f"assemble: {gate.status}" + ("" if accepted else f" ({'; '.join(gate.errors)})"), markup=False
        )
    if result.stop_reason.value != "green" or not accepted:
        raise typer.Exit(1)


NO_ORACLE = ""  # the sentinel for "do not assemble"; a real binary name is never empty

Attempt = Callable[[str, int], tuple[MarkovianResult, str]]


def _until_it_assembles(
    attempt: Attempt, task: str, nasm: str | None, repair: int
) -> tuple[MarkovianResult, str, AssembleResult | None]:
    """The first attempt plus up to *repair* retries that get NASM's errors; no gate when NASM is off."""
    result, text = attempt(task, 0)
    if nasm == NO_ORACLE:
        return result, text, None
    gate = assemble_source(text, nasm)
    for number in range(1, repair + 1):
        if gate.status != "fail":
            break
        _err.print(
            f"assemble: failed, repair attempt {number}/{repair}: {'; '.join(gate.errors)}", markup=False
        )
        result, text = attempt(_repair_task(task, text, gate), number)
        gate = assemble_source(text, nasm)
    return result, text, gate


def _repair_task(task: str, source: str, gate: AssembleResult) -> str:
    errors = wrap_untrusted("\n".join(gate.errors), "nasm")
    return (
        f"{task}\n\nYour previous attempt did not assemble. NASM reported:\n{errors}\n\n"
        f"Previous source:\n```asm\n{source}\n```\n"
        "Write the complete corrected program exactly once, in a single fenced block."
    )


def _report(result: MarkovianResult) -> None:
    _err.print(_table(result))
    for chunk in result.chunks:
        for reason in chunk.fallbacks:
            _err.print(f"chunk {chunk.index + 1} fell through: {reason}", markup=False)
    _err.print(
        f"stop_reason={result.stop_reason.value} chunks={len(result.chunks)} tokens_in={result.tokens_in} "
        f"tokens_out={result.tokens_out} peak_prompt={result.peak_tokens_in} status={result.status} "
        f"standard_cost={result.standard_cost} markovian_cost={result.markovian_cost} "
        f"efficiency={result.efficiency_percent:.1f}%",
        markup=False,
    )


def _record_stats(
    stats: Path | None, result: MarkovianResult, task: str, profile: str, recalled: int, attempt: int = 0
) -> None:
    if stats is None:
        return
    log = RunLog(stats)
    label = next((line for line in task.splitlines() if line.strip()), "(empty task)")
    suffix = f" [repair {attempt}]" if attempt else ""
    run_id = log.record(result, label=label.strip() + suffix, profile=profile, recalled=recalled)
    log.close()
    _err.print(f"stats: run {run_id} saved to {stats}")


@chunked_app.command("stats")
def stats_command(
    db: Annotated[Path, typer.Option("--db", help="Run statistics database.")] = Path("var/runs.sqlite"),
    limit: Annotated[int, typer.Option(help="How many recent runs to list.")] = 10,
) -> None:
    """Print the last runs and the totals per serving model from the statistics database."""
    if not db.exists():
        raise typer.BadParameter(f"{db} does not exist; run `chunked run --stats {db}` first")
    log = RunLog(db)
    runs = Table("run", "task", "status", "chunks", "tokens in", "tokens out", "seconds", "recalled")
    for row in log.last_runs(limit):
        runs.add_row(
            str(row.id), row.label, row.status, str(row.chunks), str(row.tokens_in), str(row.tokens_out),
            f"{row.elapsed_ms / 1000:.1f}", str(row.recalled),
        )  # fmt: skip
    models = Table("served by", "answered by", "chunks", "tokens in", "tokens out", "avg ms", "fell through")
    for model in log.per_model():
        models.add_row(
            model.served_by,
            model.answered_by or "-",
            str(model.chunks),
            str(model.tokens_in),
            str(model.tokens_out),
            str(model.avg_latency_ms),
            str(model.fell_through),
        )
    log.close()
    _out.print(runs)
    _out.print(models)
