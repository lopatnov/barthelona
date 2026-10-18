"""Real toolchain through the local agent. Needs a running ``bart-tc`` container (CI ``docker`` job)."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from barthelona.executors import AgentExecutor, Command, LocalTransport
from barthelona.toolchains.dialect import DialectAdapter
from barthelona.toolchains.gas import GasAttAdapter, GasIntelAdapter
from barthelona.toolchains.nasm import NasmAdapter

pytestmark = pytest.mark.docker

_FIXTURE = Path(__file__).parents[2] / "fixtures" / "smoke" / "hello_linux64.asm"


async def test_assemble_and_link_in_bart_tc() -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:") as archive:
        archive.add(_FIXTURE, arcname="hello.asm")

    executor = AgentExecutor(LocalTransport())
    try:
        session = await executor.open_session("docker-test", 0)
        await session.stage(buf.getvalue())
        nasm = await session.run(
            Command(argv=("nasm", "-f", "elf64", "-o", session.path("hello.o"), session.path("hello.asm")))
        )
        link = await session.run(Command(argv=("ld", "-o", session.path("hello"), session.path("hello.o"))))
        collected = await session.collect()
    finally:
        await executor.aclose()

    with tarfile.open(fileobj=io.BytesIO(collected)) as tf:
        names = tf.getnames()
    assert nasm.returncode == 0, nasm.stderr
    assert link.returncode == 0, link.stderr
    assert {"./hello.o", "./hello"} <= set(names)


@pytest.mark.parametrize(
    ("adapter", "name", "include_line"),
    [
        (NasmAdapter(), "main.asm", '%include "gen/x.inc"\n'),
        (GasIntelAdapter(), "main.s", '.include "gen/x.inc"\n'),
        (GasAttAdapter(), "main.s", '.include "gen/x.inc"\n'),
    ],
    ids=["nasm", "gas-intel", "gas-att"],
)
async def test_gen_include_resolves_in_bart_tc(adapter: DialectAdapter, name: str, include_line: str) -> None:
    """#122: a module can include ``gen/x.inc`` although ``docker exec`` starts in /work."""
    files = {name: include_line, "gen/x.inc": "; generated\n"}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:") as archive:
        for arcname, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(arcname)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))

    executor = AgentExecutor(LocalTransport())
    try:
        session = await executor.open_session("docker-include", 0)
        await session.stage(buf.getvalue())
        result = await session.run(Command(argv=adapter.syntax_check_argv(session.path(name))))
    finally:
        await executor.aclose()

    assert result.returncode == 0, result.stderr


async def test_run_in_bart_run_sandbox() -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:") as archive:
        archive.add(_FIXTURE, arcname="hello.asm")

    executor = AgentExecutor(LocalTransport())
    try:
        build = await executor.open_session("docker-sandbox", 0)
        await build.stage(buf.getvalue())
        obj = build.path("hello.o")
        await build.run(Command(argv=("nasm", "-f", "elf64", "-o", obj, build.path("hello.asm"))))
        await build.run(Command(argv=("ld", "-o", build.path("hello"), obj)))

        sandbox = await executor.sandbox().open_session("docker-sandbox", 0)
        ran = await sandbox.run(Command(argv=(sandbox.path("hello"),)))
        echoed = await sandbox.run(Command(argv=("cat",), stdin=b"golden\n"))
        write = await sandbox.run(Command(argv=("touch", sandbox.path("new-file"))))
    finally:
        await executor.aclose()

    assert (ran.returncode, ran.stdout) == (0, b"ok\n"), ran.stderr
    assert echoed.stdout == b"golden\n"
    assert write.returncode != 0  # /work is mounted read-only
