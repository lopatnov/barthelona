"""The training-data setting (D-036): off unless the owner turns it on."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DIRECTORY = Path("var/training")


class TrainingDataSettings(BaseSettings):
    """Read from `BARTHELONA_TRAINING_DATA_ENABLED` and `BARTHELONA_TRAINING_DATA_DIRECTORY`.

    Only the process environment is read, never `.env` (invariant 10). A relative directory is resolved
    against the working directory, which is the repository root for `scripts/run.ps1`.
    """

    model_config = SettingsConfigDict(env_prefix="BARTHELONA_TRAINING_DATA_", frozen=True, extra="ignore")

    enabled: bool = False
    directory: Path = DEFAULT_DIRECTORY
