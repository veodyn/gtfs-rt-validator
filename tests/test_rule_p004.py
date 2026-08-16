"""P004: a header interval in the band between the document's 30 and W007's 35.

The band is two-sided and both edges are measured rather than argued. Against
the pinned jar, one invocation per interval over a two-file run:

| interval | jar |
|---|---|
| 20 | nothing |
| 30 | nothing |
| 33 | nothing |
| 35 | nothing |
| 36 | W007 |
| 40 | W007 |

So W007's comparison is strictly greater than 35, and 35 is P004's, not
upstream's. `tests/test_practice_tier_does_not_shadow_the_jar.py` is where that
measurement lives as an assertion; this file is the rule's own behaviour.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.rules.practice.p004 import check
from specfixtures import context, message, prefixes

CLOCK = 1_700_000_000


def run(previous_timestamp: int | None, timestamp: int | None):
    """One message against a previous one. `None` states no timestamp at all."""
    current = message(timestamp=timestamp) if timestamp is not None else message()
    if previous_timestamp is None:
        return check(current, context())
    return check(current, context(previous=message(timestamp=previous_timestamp)))


@pytest.mark.parametrize("interval", [31, 33, 34, 35])
def test_an_interval_inside_the_band_is_reported(interval):
    """The upper edge is inclusive: 35 is W007's threshold and W007 is strict,
    so the second the interval reaches 35 nobody but P004 has anything to say."""
    found = run(CLOCK, CLOCK + interval)

    expected = (
        f"{interval} second interval between consecutive header.timestamps, "
        "which is more than the recommended 30"
    )

    assert prefixes(found) == [expected]


@pytest.mark.parametrize("interval", [0, 1, 29, 30])
def test_an_interval_the_document_allows_is_silent(interval):
    """30 is the boundary on the compliant side. "At least once every 30
    seconds" is satisfied by exactly 30, so 30 is nobody's finding."""
    assert prefixes(run(CLOCK, CLOCK + interval)) == []


@pytest.mark.parametrize("interval", [36, 40, 3600])
def test_an_interval_w007_reaches_is_left_to_w007(interval):
    """The other side of the band. A rule that fired here would report the same
    feed twice, which is the whole thing decision 3 is arranging against."""
    assert prefixes(run(CLOCK, CLOCK + interval)) == []


def test_a_decreasing_interval_is_e018s_and_not_this_rules():
    assert prefixes(run(CLOCK + 33, CLOCK)) == []


def test_the_first_message_of_a_run_has_no_interval():
    assert prefixes(run(None, CLOCK)) == []


@pytest.mark.parametrize(
    ("previous", "current"),
    [(0, CLOCK + 33), (CLOCK, 0), (None, None)],
    ids=["previous absent", "current absent", "neither stated"],
)
def test_an_absent_header_timestamp_is_not_an_interval(previous, current):
    """A zero header timestamp is an absent one, which is W001's or E048's
    finding. Reading it as 1970 would make P004 fire on any feed whose previous
    message declared nothing at all."""
    current_message = message() if current is None else message(timestamp=current)
    previous_message = message() if previous is None else message(timestamp=previous)

    assert prefixes(check(current_message, context(previous=previous_message))) == []


def test_the_occurrence_carries_the_interval_and_both_timestamps():
    (found,) = list(run(CLOCK, CLOCK + 33))

    assert found.context == {
        "entityPath": "header",
        "intervalSeconds": 33,
        "previousTimestamp": CLOCK,
        "timestamp": CLOCK + 33,
    }


def test_the_band_stops_exactly_where_upstreams_constant_starts():
    """The upper edge is imported from `_shared/timestamp_pass`, not written
    out, so a pin that moved W007's threshold would move this band with it
    rather than opening a gap or an overlap between the two."""
    from gtfs_rt_validator.rules._shared.timestamp_pass import MINIMUM_REFRESH_INTERVAL_SECONDS
    from gtfs_rt_validator.rules.practice.p004 import BAND_UPPER

    assert BAND_UPPER == MINIMUM_REFRESH_INTERVAL_SECONDS
