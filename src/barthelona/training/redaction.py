"""Secret redaction for texts that enter the training dataset (invariant 10, architecture §21)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

REDACTED = "[REDACTED]"
# Shorter values are too likely to occur in ordinary text, and redacting them would corrupt samples.
MIN_SECRET_LENGTH = 8
# Key shapes of the configured cloud providers, caught even when the caller did not pass the value.
# The lookbehind keeps ids such as `task-...` or `disk-...` intact.
_KEY_SHAPES = re.compile(
    r"(?<![A-Za-z0-9_-])(?:sk-ant-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35})"
)


@dataclass(frozen=True, slots=True)
class Redactor:
    """Replaces known secret values and API-key-shaped tokens with `REDACTED`."""

    secrets: tuple[str, ...] = field(default=(), repr=False)  # never printed in logs or tracebacks

    @classmethod
    def of(cls, secrets: Iterable[str]) -> Redactor:
        usable = {secret for secret in secrets if len(secret) >= MIN_SECRET_LENGTH}
        # Longest first, so a secret that contains another is replaced whole.
        return cls(tuple(sorted(usable, key=len, reverse=True)))

    def __call__(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, REDACTED)
        return _KEY_SHAPES.sub(REDACTED, text)
