"""Real toolchain through the local agent. Needs a running ``bart-tc`` container (CI ``docker`` job)."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from barthelona.executors import AgentExecutor, Command, LocalTransport

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
