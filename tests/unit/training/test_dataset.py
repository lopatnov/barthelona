"""The training dataset: off by default, local files only, secrets redacted, code kept out of the index."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from barthelona.cli import app
from barthelona.domain import (
    ABI,
    OS,
    Arch,
    Dialect,
    Level,
    LevelResult,
    Linker,
    ObjFormat,
    Role,
    RunEnv,
    SampleSource,
    TargetProfile,
    TrainingAttempt,
    Verdict,
)
from barthelona.training import (
    REDACTED,
    DatasetError,
    DatasetReader,
    DatasetWriter,
    DisabledSink,
    Redactor,
    TrainingDataSettings,
    count_verdicts,
    open_sink,
)

PROMPT = "Implement bart_strlen (rdi: char*, rax: u64) in src/strlen.asm.\r\n"
RESPONSE = "FILE src/strlen.asm\nbart_strlen:\n    xor eax, eax\n    ret\n"
SECRET = "sk-test-0123456789abcdef"


def _attempt(seq: int, *, failed: bool = False, improves_on_seq: int | None = None) -> TrainingAttempt:
    target = TargetProfile(
        preset="linux-x64-nasm-static",
        dialect=Dialect.NASM,
        arch=Arch.X86_64,
        os=OS.LINUX,
        abi=ABI.SYSV64,
        obj_format=ObjFormat.ELF64,
        link=Linker.LD,
        run_env=RunEnv.DOCKER_NATIVE,
    )
    return TrainingAttempt(
        run_id="r1",
        source=SampleSource.RUN,
        seq=seq,
        recorded_at=datetime(2026, 10, 14, tzinfo=UTC),
        target=target,
        node_id="code",
        role=Role.WORKER,
        attempt=seq + 1,
        provider="lmstudio",
        model="qwen3-coder-30b-a3b",
        local=True,
        levels=[LevelResult(level=Level.V0, status="fail" if failed else "pass", secs=0.2)],
        improves_on_seq=improves_on_seq,
    )


def test_collection_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BARTHELONA_TRAINING_DATA_ENABLED", raising=False)
    monkeypatch.delenv("BARTHELONA_TRAINING_DATA_DIRECTORY", raising=False)
    settings = TrainingDataSettings()
    assert settings.enabled is False
    assert settings.directory == Path("var/training")


def test_the_setting_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BARTHELONA_TRAINING_DATA_ENABLED", "1")
    monkeypatch.setenv("BARTHELONA_TRAINING_DATA_DIRECTORY", str(tmp_path))
    assert TrainingDataSettings() == TrainingDataSettings(enabled=True, directory=tmp_path)


def test_a_disabled_setting_writes_nothing(tmp_path: Path) -> None:
    sink = open_sink(TrainingDataSettings(enabled=False, directory=tmp_path / "ds"), secrets=[])
    assert isinstance(sink, DisabledSink)
    assert sink.record(_attempt(0), prompt=PROMPT, response=RESPONSE) is None
    assert not (tmp_path / "ds").exists()


def test_an_enabled_setting_records_the_attempt_and_its_texts(tmp_path: Path) -> None:
    sink = open_sink(TrainingDataSettings(enabled=True, directory=tmp_path), secrets=[])
    sample = sink.record(_attempt(0), prompt=PROMPT, response=RESPONSE)

    reader = DatasetReader(tmp_path)
    assert list(reader.samples()) == [sample]
    assert sample is not None
    assert reader.text(sample.prompt_sha256) == PROMPT  # byte-exact, CRLF included
    assert reader.text(sample.response_sha256) == RESPONSE


def test_code_stays_out_of_the_index(tmp_path: Path) -> None:
    DatasetWriter(tmp_path, Redactor()).record(_attempt(0), prompt=PROMPT, response=RESPONSE)
    index = (tmp_path / "samples.jsonl").read_text(encoding="utf-8")
    assert "xor eax" not in index
    assert "bart_strlen" not in index


def test_shared_texts_are_stored_once(tmp_path: Path) -> None:
    writer = DatasetWriter(tmp_path, Redactor())
    writer.record(_attempt(0, failed=True), prompt=PROMPT, response="FILE src/strlen.asm\nbad\n")
    writer.record(_attempt(1, improves_on_seq=0), prompt=PROMPT, response=RESPONSE)
    assert len(list((tmp_path / "texts").rglob("*.txt"))) == 3


def test_verdicts_are_counted_for_the_preference_pair(tmp_path: Path) -> None:
    writer = DatasetWriter(tmp_path, Redactor())
    writer.record(_attempt(0, failed=True), prompt=PROMPT, response="bad")
    writer.record(_attempt(1, improves_on_seq=0), prompt=PROMPT, response=RESPONSE)
    samples = list(DatasetReader(tmp_path).samples())
    assert count_verdicts(samples) == {Verdict.REJECTED: 1, Verdict.ACCEPTED: 1}
    assert samples[1].attempt.improves_on_seq == samples[0].attempt.seq


def test_secrets_are_redacted_before_anything_is_written(tmp_path: Path) -> None:
    writer = DatasetWriter(tmp_path, Redactor.of([SECRET]))
    sample = writer.record(_attempt(0), prompt=f"key={SECRET}", response="AIza" + "x" * 35)
    reader = DatasetReader(tmp_path)
    assert reader.text(sample.prompt_sha256) == f"key={REDACTED}"
    assert reader.text(sample.response_sha256) == REDACTED
    on_disk = b"".join(path.read_bytes() for path in tmp_path.rglob("*") if path.is_file())
    assert SECRET.encode() not in on_disk


def test_short_values_are_not_treated_as_secrets() -> None:
    assert Redactor.of(["ab", ""])("mov rax, ab") == "mov rax, ab"


def test_ids_that_resemble_key_prefixes_are_kept() -> None:
    assert Redactor()("task-abcdefghijklmnopqrstuvwxyz disk-0123456789abcdefghijk") == (
        "task-abcdefghijklmnopqrstuvwxyz disk-0123456789abcdefghijk"
    )


def test_the_redactor_never_prints_its_secrets() -> None:
    assert SECRET not in repr(Redactor.of([SECRET]))


def test_a_missing_dataset_is_empty(tmp_path: Path) -> None:
    assert list(DatasetReader(tmp_path / "none").samples()) == []


def test_a_corrupt_index_line_is_reported_with_its_number(tmp_path: Path) -> None:
    DatasetWriter(tmp_path, Redactor()).record(_attempt(0), prompt=PROMPT, response=RESPONSE)
    with (tmp_path / "samples.jsonl").open("a", encoding="utf-8", newline="\n") as index:
        index.write("{not json\n")
    with pytest.raises(DatasetError, match=r"samples\.jsonl:2:"):
        list(DatasetReader(tmp_path).samples())


def test_cli_status_reports_a_corrupt_dataset_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "samples.jsonl").write_text("{truncated\n", encoding="utf-8")
    monkeypatch.setenv("BARTHELONA_TRAINING_DATA_DIRECTORY", str(tmp_path))
    result = CliRunner().invoke(app, ["training", "status"])
    assert result.exit_code == 1
    assert "samples.jsonl:1:" in result.stderr
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_cli_status_reports_the_setting_and_counts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    DatasetWriter(tmp_path, Redactor()).record(_attempt(0), prompt=PROMPT, response=RESPONSE)
    monkeypatch.setenv("BARTHELONA_TRAINING_DATA_ENABLED", "0")
    monkeypatch.setenv("BARTHELONA_TRAINING_DATA_DIRECTORY", str(tmp_path))
    result = CliRunner().invoke(app, ["training", "status"])
    assert result.exit_code == 0, result.stdout
    assert "collection: disabled" in result.stdout
    assert "accepted: 1" in result.stdout
    assert "rejected: 0" in result.stdout
