"""Pydantic models for ``config/toolchains.lock.json`` (architecture §12)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ToolInfo(BaseModel):
    """A single tool discovered during the toolchain probe."""

    version: str = Field(description="First line of the tool's --version output.")
    path: str = Field(description="Absolute path inside the container (from 'which').")


class ToolchainLock(BaseModel):
    """The toolchain lock file written by ``barthelona probe``.

    Stores the Docker image digests and the version of every tool inside
    the ``bart-tc`` container, so :class:`ToolchainResolver` can plan
    (dialect, target) → executor pairs and the UI can show what is installed.
    """

    toolchain_image_digest: str = Field(
        description="Digest of the bart-tc Docker image (e.g. 'sha256:…')."
    )
    runner_image_digest: str = Field(
        description="Digest of the bart-run Docker image (e.g. 'sha256:…').",
        default="",
    )
    tools: dict[str, ToolInfo] = Field(
        description="Map of tool name to version and path inside bart-tc.",
        default_factory=dict,
    )
    probed_at: datetime = Field(description="UTC timestamp when the probe ran.")
