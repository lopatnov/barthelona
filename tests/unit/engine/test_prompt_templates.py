"""The JSON shapes in the prompts are filled-in examples: a model must never see a `<placeholder>` to copy."""

from __future__ import annotations

import re

from barthelona.engine import spec, tests_author

PLACEHOLDER = re.compile(r"<[^<>\n]+>")


def test_no_prompt_shows_an_angle_bracket_placeholder() -> None:
    for prompt in (spec._INTAKE_PROMPT, spec._SPEC_PROMPT, tests_author._PROMPT):
        assert PLACEHOLDER.search(prompt) is None
