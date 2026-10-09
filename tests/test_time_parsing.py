"""``TimeUtils.parse``: the fast path must accept everything the old one did."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.utils.time_utils import TimeUtils


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-03-02T08:05:00", datetime(2026, 3, 2, 8, 5)),
        ("2026-03-02T08:05:00.123456", datetime(2026, 3, 2, 8, 5, 0, 123456)),
        ("2026-03-02T08:05:00.5", datetime(2026, 3, 2, 8, 5, 0, 500000)),
        ("  2026-03-02T08:05:00  ", datetime(2026, 3, 2, 8, 5)),
        ("2026-03-02 08:05:00", datetime(2026, 3, 2, 8, 5)),
        ("2026-03-02T08:05", datetime(2026, 3, 2, 8, 5)),
        ("2026-03-02", datetime(2026, 3, 2)),
        ("20260302T080500", datetime(2026, 3, 2, 8, 5)),
    ],
)
def test_parses_every_stored_shape(value, expected):
    assert TimeUtils.parse(value) == expected


@pytest.mark.parametrize("value", ["", None, "   ", "not a time", "08:05:00", "2026-13-45T99:99:99"])
def test_rejects_what_it_never_accepted(value):
    assert TimeUtils.parse(value) is None


def test_a_trailing_z_keeps_its_offset():
    parsed = TimeUtils.parse("2026-03-02T08:05:00Z")
    assert parsed is not None
    assert parsed.utcoffset() is not None


def test_round_trips_a_stored_timestamp():
    moment = datetime(2026, 3, 2, 8, 5, 9)
    assert TimeUtils.parse(TimeUtils.to_iso(moment)) == moment


def test_fromisoformat_is_tried_before_strptime():
    """Guards against the slow order creeping back in."""
    import inspect

    source = inspect.getsource(TimeUtils.parse)
    assert source.index("fromisoformat") < source.index("strptime")


def test_parse_is_much_faster_than_strptime():
    """A regression here means reports and the dashboard slow down again."""
    import time

    value = "2026-03-02T08:05:00"
    repeats = 20000

    start = time.perf_counter()
    for _ in range(repeats):
        TimeUtils.parse(value)
    fast = time.perf_counter() - start

    start = time.perf_counter()
    for _ in range(repeats):
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    slow = time.perf_counter() - start

    assert fast < slow, f"parse {fast:.3f}s is not faster than strptime {slow:.3f}s"
