"""E025, a stop_time_update whose departure is before its own arrival.

`testE025` (`TimestampValidatorTest.java:961-1046`) is upstream's, ported stage by
stage from the checkout at `jar-build/upstream/`. Upstream asserts counts only;
everything below `UPSTREAM_CASES` is ours.

The rule is a within-stop comparison, which is what separates it from E022 next
to it in the same block. Every stage builds one stop_time_update, so no E022
comparison has a previous stop to reach for and the counts are E025's alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.times import MIN_POSIX_TIME, posix_to_clock
from gtfs_rt_validator.rules.upstream.e025 import RULE_ID, check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from rulefixtures import ENTITY_ID, TESTAGENCY_TIMEZONE, context, entity, message, prefixes
from rulefixtures import occurrences as found_occurrences

NOW = Reading(MIN_POSIX_TIME * 1000, ClockSource.FIXED)


def a_feed(arrival: int | None, departure: int | None, **fields: object) -> Msg:
    """`testE025`'s entity: one TripUpdate carrying one stop_time_update."""
    stop: dict[str, object] = dict(fields)
    if arrival is not None:
        stop["arrival"] = {"time": MIN_POSIX_TIME + arrival}
    if departure is not None:
        stop["departure"] = {"time": MIN_POSIX_TIME + departure}
    return message(
        entity(
            trip_update={
                "trip": {},
                "timestamp": MIN_POSIX_TIME,
                "stop_time_update": [stop] if stop else [],
            },
            vehicle={"timestamp": MIN_POSIX_TIME},
        ),
        timestamp=MIN_POSIX_TIME,
    )


#: `testE025` in order: the stop's arrival and departure as offsets from
#: `MIN_POSIX_TIME`, `None` for a stop with no stop_time_update at all, and the
#: count upstream asserts.
UPSTREAM_CASES = (
    ((None, None), 0),
    ((0, 0), 0),
    ((0, 1), 0),
    ((1, 0), 1),
)


@pytest.mark.parametrize(("times", "expected"), UPSTREAM_CASES)
def test_upstream_cases(
    tmp_path: Path, times: tuple[int | None, int | None], expected: int
) -> None:
    feed = a_feed(*times)

    assert len(found_occurrences(check(feed, context(tmp_path, clock=NOW)))) == expected


def moment(offset: int) -> str:
    value = MIN_POSIX_TIME + offset
    return f"{posix_to_clock(value, TESTAGENCY_TIMEZONE)} ({value})"


def test_the_prefix_names_both_times_of_the_same_stop(tmp_path: Path) -> None:
    """`:248-251`, and it says "the same stop" where E022 says "previous stop"."""
    expected = (
        f"entity ID {ENTITY_ID} stop_id  departure_time {moment(0)} "
        f"is less than the same stop arrival_time {moment(1)}"
    )

    assert prefixes(check(a_feed(1, 0), context(tmp_path, clock=NOW))) == [expected]


def test_an_arrival_with_no_time_is_not_compared(tmp_path: Path) -> None:
    """`stopTimeUpdate.getArrival().hasTime()` (`:246`), read with no
    `hasArrival()` guard. That is safe rather than a bug: an absent arrival
    decodes to the default instance, whose `hasTime()` is false, so a
    departure-only stop is never compared against a time of 0."""
    assert prefixes(check(a_feed(None, 0), context(tmp_path, clock=NOW))) == []


def test_a_departure_with_no_time_is_not_compared(tmp_path: Path) -> None:
    """The whole block is inside `hasDeparture() && departure.hasTime()` (`:217-218`)."""
    assert prefixes(check(a_feed(0, None), context(tmp_path, clock=NOW))) == []


def test_it_is_a_within_stop_comparison_and_never_a_between_stop_one(tmp_path: Path) -> None:
    """Two stops whose times each increase within the stop but decrease between
    them: E022's business entirely, and this rule reports nothing."""
    feed = message(
        entity(
            trip_update={
                "trip": {},
                "timestamp": MIN_POSIX_TIME,
                "stop_time_update": [
                    {
                        "arrival": {"time": MIN_POSIX_TIME + 8},
                        "departure": {"time": MIN_POSIX_TIME + 9},
                    },
                    {
                        "arrival": {"time": MIN_POSIX_TIME + 1},
                        "departure": {"time": MIN_POSIX_TIME + 2},
                    },
                ],
            }
        ),
        timestamp=MIN_POSIX_TIME,
    )

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == []


def test_the_agency_timezone_reaches_both_clocks(tmp_path: Path) -> None:
    in_tokyo = context(tmp_path, clock=NOW, timezone="Asia/Tokyo")

    expected = (
        f"entity ID {ENTITY_ID} stop_id  departure_time 09:00:00 ({MIN_POSIX_TIME}) "
        f"is less than the same stop arrival_time 09:00:01 ({MIN_POSIX_TIME + 1})"
    )

    assert prefixes(check(a_feed(1, 0), in_tokyo)) == [expected]


def test_the_occurrence_locates_the_stop(tmp_path: Path) -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone."""
    (one,) = found_occurrences(check(a_feed(1, 0), context(tmp_path, clock=NOW)))

    assert (one.rule_id, one.context[ENTITY_PATH_KEY]) == (
        RULE_ID,
        "entity[0].trip_update.stop_time_update[0]",
    )
