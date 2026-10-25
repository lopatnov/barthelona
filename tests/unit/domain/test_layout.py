"""The run-folder layout that the UI, the CLI and the worker must agree on (invariant 8, docs §18)."""

from __future__ import annotations

from pathlib import Path

from barthelona.domain.layout import REQUEST_FILE, RUNS_DIR, SPEC_FILE, TESTS_FILE, run_dir


def test_a_run_gets_one_folder_named_after_it() -> None:
    assert run_dir(Path("var/runs"), "run-1") == Path("var/runs/run-1")
    assert run_dir(Path("elsewhere"), "run-2") == Path("elsewhere/run-2")


def test_the_file_names_the_ui_writes_are_the_ones_the_worker_reads() -> None:
    # Changing one of these silently disconnects the side that writes a file from the side that reads it.
    assert Path("var/runs") == RUNS_DIR
    assert (REQUEST_FILE, SPEC_FILE, TESTS_FILE) == ("request.txt", "spec.json", "tests.json")
