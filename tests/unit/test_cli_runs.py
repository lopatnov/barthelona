"""`runs submit|status|decide`: the CLI side of the run store, the same rows the UI writes."""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from barthelona.cli import app
from barthelona.domain import CommandKind, GateKind, GateRequest, Profile, RunStatus
from barthelona.domain.layout import REQUEST_FILE
from barthelona.persistence import open_store


def _invoke(tmp_path: Path, *args: str):  # type: ignore[no-untyped-def]  # typer's Result type is not exported
    return CliRunner().invoke(app, ["runs", *args, "--db", str(tmp_path / "app.sqlite")])


def _submit(tmp_path: Path, *extra: str) -> str:
    result = _invoke(tmp_path, "submit", "Print hello.", "--runs", str(tmp_path / "runs"), *extra)
    assert result.exit_code == 0, result.output
    return result.output.strip()


def test_submit_queues_a_meterless_run_and_writes_the_request(tmp_path: Path) -> None:
    run_id = _submit(tmp_path)
    assert (tmp_path / "runs" / run_id / REQUEST_FILE).read_text(encoding="utf-8") == "Print hello."
    with closing(open_store(tmp_path / "app.sqlite")) as store:
        run = store.get_run(run_id)
    assert (run.status, run.profile, run.target.preset) == (
        RunStatus.QUEUED,
        Profile.METERLESS,
        "linux-x64-nasm-static",
    )
    assert run.budget.cloud_allowed


def test_submit_with_a_project_name_puts_the_run_in_that_demos_folder(tmp_path: Path) -> None:
    run_id = _submit(tmp_path, "--project", "simplest-demo-en")
    with closing(open_store(tmp_path / "app.sqlite")) as store:
        assert store.get_run(run_id).workspace == "demos/simplest-demo-en"


def test_submit_rejects_a_project_name_that_is_not_a_slug(tmp_path: Path) -> None:
    result = _invoke(tmp_path, "submit", "Print hello.", "--project", "../etc", "--runs", str(tmp_path / "r"))
    assert result.exit_code != 0
    assert not (tmp_path / "r").exists()


def test_submit_rejects_an_unknown_preset(tmp_path: Path) -> None:
    result = _invoke(tmp_path, "submit", "x", "--preset", "win-x64-masm", "--runs", str(tmp_path / "runs"))
    assert result.exit_code == 2
    assert "linux-x64-nasm-static" in result.output


def test_decide_answers_the_one_open_gate_and_status_shows_it(tmp_path: Path) -> None:
    run_id = _submit(tmp_path)
    with closing(open_store(tmp_path / "app.sqlite")) as store:
        store.open_gate(
            GateRequest(
                gate_id=f"{run_id}-G1", kind=GateKind.G1_SPEC, run_id=run_id, options=["approve", "reject"]
            )
        )
    assert "approve" in _invoke(tmp_path, "status", run_id, "--runs", str(tmp_path / "runs")).output
    assert _invoke(tmp_path, "decide", run_id, "approve").exit_code == 0
    with closing(open_store(tmp_path / "app.sqlite")) as store:
        [command] = store.claim_commands(run_id)
    assert command.kind is CommandKind.RESUME
    assert command.decision is not None
    assert (command.decision.decision, command.decision.at.date()) == ("approve", datetime.now(UTC).date())


def test_decide_without_an_open_gate_is_an_error(tmp_path: Path) -> None:
    run_id = _submit(tmp_path)
    result = _invoke(tmp_path, "decide", run_id, "approve")
    assert result.exit_code == 2
    assert "0 open gates" in result.output


def test_a_run_waits_for_a_human_unless_auto_approve_is_asked_for(tmp_path: Path) -> None:
    plain = _submit(tmp_path)
    auto = _submit(tmp_path, "--auto-approve")
    with closing(open_store(tmp_path / "app.sqlite")) as store:
        assert (store.get_run(plain).auto_approve, store.get_run(auto).auto_approve) == (False, True)


def test_a_run_is_packaged_when_green_unless_no_package_is_asked_for(tmp_path: Path) -> None:
    default = _submit(tmp_path)
    manual = _submit(tmp_path, "--no-package")
    with closing(open_store(tmp_path / "app.sqlite")) as store:
        assert (store.get_run(default).auto_package, store.get_run(manual).auto_package) == (True, False)
