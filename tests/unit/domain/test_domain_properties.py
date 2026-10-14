"""Property tests for domain validators: they accept exactly the values their rule describes."""

from __future__ import annotations

from itertools import pairwise

from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from barthelona.domain.contracts import StructDef, StructField


@given(
    offsets=st.lists(st.integers(min_value=0, max_value=4096), min_size=1, max_size=8),
    size=st.integers(min_value=1, max_value=4097),
)
def test_struct_layout_is_valid_exactly_when_offsets_ascend_inside_the_size(
    offsets: list[int], size: int
) -> None:
    fields = [StructField(name=f"f{n}", type="u64", off=off) for n, off in enumerate(offsets)]
    expected_valid = all(a < b for a, b in pairwise(offsets)) and offsets[-1] < size
    try:
        StructDef(fields=fields, size=size)
    except ValidationError:
        assert not expected_valid
    else:
        assert expected_valid
