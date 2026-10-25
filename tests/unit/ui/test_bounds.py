"""The bounds the UI states are the ones the engine enforces; the form no longer offers sprints."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from barthelona.engine import codegen
from barthelona.ui.bounds import CODE_ATTEMPTS, CODE_CHUNKS, REAL_BOUNDS


def test_the_stated_bounds_match_the_code_step() -> None:
    assert CODE_ATTEMPTS == codegen.REPAIRS + 1
    assert codegen.CHUNKS.max_chunks == CODE_CHUNKS


def test_the_new_request_form_has_no_sprints_box_and_states_the_real_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def page() -> None:
        from barthelona.ui.pages.new_request import page_new_request

        page_new_request()

    monkeypatch.chdir(tmp_path)

    app = AppTest.from_function(page, default_timeout=30).run()

    assert not app.exception
    assert not [box for box in app.number_input if "sprint" in box.label.lower()]
    assert any(REAL_BOUNDS in caption.value for caption in app.caption)
