"""Property-based fuzzing: the parser must never crash uncaught (DESIGN.md §12).

For arbitrary JSON-shaped input, ``parse_status`` must either return a valid
schema or raise ``pydantic.ValidationError`` — never an unexpected exception type.
This guarantees malformed upstream data is always quarantined cleanly rather than
taking down the pipeline.
"""

from __future__ import annotations

import contextlib

from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from archiver.parsing import parse_status

_json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=12),
    lambda children: st.lists(children, max_size=4)
    | st.dictionaries(st.text(max_size=8), children, max_size=4),
    max_leaves=15,
)


@given(st.dictionaries(st.text(max_size=8), _json_values, max_size=8))
def test_parse_status_never_raises_uncaught(data: dict[str, object]) -> None:
    # ValidationError is the only acceptable failure mode; anything else fails the test.
    with contextlib.suppress(ValidationError):
        parse_status(data)
