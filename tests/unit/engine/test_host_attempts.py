"""The code step's drafts reach the run folder while it works."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

from barthelona.engine.host import no_facts, services_for
from barthelona.llm import FakeGateway
from barthelona.persistence import Store, connect, migrate


def test_each_attempt_is_written_to_its_own_file_in_the_run_folder(tmp_path: Path) -> None:
    conn = connect(tmp_path / "app.sqlite")
    migrate(conn)
    with closing(conn):
        services = services_for(Store(conn), tmp_path / "runs", lambda _run: FakeGateway([]), no_facts)
        services.save_attempt("r1", 1, "mov rax, 1")
        services.save_attempt("r1", 2, "mov rax, 60")

    folder = tmp_path / "runs" / "r1"
    assert (folder / "attempt-1.asm").read_text(encoding="utf-8") == "mov rax, 1\n"
    assert (folder / "attempt-2.asm").read_text(encoding="utf-8") == "mov rax, 60\n"
    assert not (folder / "main.asm").exists()  # main.asm is only for the accepted program
