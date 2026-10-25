"""Paging of the Live Run lists: newest page first, every entry reachable."""

from __future__ import annotations

import pytest

from barthelona.ui.paging import page_count, page_slice


@pytest.mark.parametrize(("total", "size", "pages"), [(0, 10, 1), (10, 10, 1), (11, 10, 2), (95, 25, 4)])
def test_page_count_rounds_up_and_is_at_least_one(total: int, size: int, pages: int) -> None:
    assert page_count(total, size) == pages


def test_page_zero_is_the_newest_entries_and_the_last_page_holds_the_oldest() -> None:
    assert page_slice(25, 0, 10) == (15, 25)
    assert page_slice(25, 1, 10) == (5, 15)
    assert page_slice(25, 2, 10) == (0, 5)


def test_a_page_out_of_range_is_clamped() -> None:
    assert page_slice(25, 9, 10) == (0, 5)
    assert page_slice(25, -1, 10) == (15, 25)
    assert page_slice(0, 0, 10) == (0, 0)


def test_every_entry_is_on_exactly_one_page() -> None:
    seen = [i for page in range(page_count(103, 25)) for i in range(*page_slice(103, page, 25))]

    assert sorted(seen) == list(range(103))
