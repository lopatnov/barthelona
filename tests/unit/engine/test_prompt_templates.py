"""The JSON shapes in the prompts are filled-in examples: a model must never see a `<placeholder>` to copy."""

from __future__ import annotations

import re

import orjson

from barthelona.engine import spec, tests_author

PLACEHOLDER = re.compile(r"<[^<>\n]+>")


def test_no_prompt_shows_an_angle_bracket_placeholder() -> None:
    for prompt in (spec._INTAKE_PROMPT, spec._SPEC_PROMPT, tests_author._PROMPT):
        assert PLACEHOLDER.search(prompt) is None


def _example(prompt: str) -> bytes:
    """The JSON object a prompt shows the model: from 'nothing else:' up to 'That example'."""
    return prompt.split("nothing else:\n", 1)[1].split("\nThat example", 1)[0].encode("utf-8")


def test_the_intake_example_is_a_valid_intake() -> None:
    assert spec.Intake.model_validate(orjson.loads(_example(spec._INTAKE_PROMPT))).lang == "de"


def test_the_spec_example_is_a_valid_spec_draft() -> None:
    draft = spec.SpecDraft.model_validate(orjson.loads(_example(spec._SPEC_PROMPT)))

    assert [requirement.id for requirement in draft.requirements] == ["R1"]


def test_the_test_author_example_is_a_valid_tests_draft() -> None:
    draft = tests_author.TestsDraft.model_validate(orjson.loads(_example(tests_author._PROMPT)))

    assert [test.id for test in draft.tests] == ["T1", "T2"]
