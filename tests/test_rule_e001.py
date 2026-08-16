"""E001, a time outside the POSIX window, from all seven of its emission sites.

`testE001` (`TimestampValidatorTest.java:268-424`) is upstream's, ported stage by
stage from the checkout at `jar-build/upstream/`. Its `BAD_TIME` is
`MIN_POSIX_TIME` expressed in milliseconds, which is the producer error the rule
exists to catch: a feed publishing epoch milliseconds where seconds were meant.

Upstream asserts counts only, and its eight stages happen to cover six of the
seven sites; the seventh, a stop_time_update departure, is only ever exercised
alongside its arrival. Everything below `UPSTREAM_CASES` is ours, including the
one feed that fires all seven at once and pins their order.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.times import MAX_POSIX_TIME, MIN_POSIX_TIME
from gtfs_rt_validator.rules.upstream.e001 import RULE_ID, check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from rulefixtures import ENTITY_ID, context, entity, message, occurrences, prefixes

NOW = Reading(MIN_POSIX_TIME * 1000, ClockSource.FIXED)

#: `testE001`'s `BAD_TIME`: a valid POSIX second expressed in milliseconds.
BAD_TIME = MIN_POSIX_TIME * 1000


def a_feed(
    header: int,
    trip_update: int,
    vehicle: int,
    stop_times: Sequence[tuple[int, int]] = (),
    active_periods: Sequence[tuple[int, int]] = (),
) -> Msg:
    """`testE001`'s one entity, with its stop_time_updates and alert as pairs."""
    trip: dict[str, object] = {"trip": {}, "timestamp": trip_update}
    if stop_times:
        trip["stop_time_update"] = [
            {"arrival": {"time": arrival}, "departure": {"time": departure}}
            for arrival, departure in stop_times
        ]
    alert = None
    if active_periods:
        alert = {"active_period": [{"start": start, "end": end} for start, end in active_periods]}
    return message(
        entity(trip_update=trip, vehicle={"timestamp": vehicle}, alert=alert),
        timestamp=header,
    )


#: `testE001` in order: the feed, and the count upstream asserts for it.
UPSTREAM_CASES: tuple[tuple[dict[str, object], int], ...] = (
    ({"header": MIN_POSIX_TIME, "trip_update": MIN_POSIX_TIME, "vehicle": MIN_POSIX_TIME}, 0),
    ({"header": BAD_TIME, "trip_update": MIN_POSIX_TIME, "vehicle": MIN_POSIX_TIME}, 1),
    ({"header": BAD_TIME, "trip_update": BAD_TIME, "vehicle": MIN_POSIX_TIME}, 2),
    ({"header": BAD_TIME, "trip_update": BAD_TIME, "vehicle": BAD_TIME}, 3),
    (
        {
            "header": MIN_POSIX_TIME,
            "trip_update": MIN_POSIX_TIME,
            "vehicle": MIN_POSIX_TIME,
            "stop_times": ((MIN_POSIX_TIME, MIN_POSIX_TIME), (MAX_POSIX_TIME, MAX_POSIX_TIME)),
        },
        0,
    ),
    (
        {
            "header": MIN_POSIX_TIME,
            "trip_update": MIN_POSIX_TIME,
            "vehicle": MIN_POSIX_TIME,
            "stop_times": ((BAD_TIME, BAD_TIME), (BAD_TIME + 1, BAD_TIME + 1)),
        },
        4,
    ),
    (
        {
            "header": MIN_POSIX_TIME,
            "trip_update": MIN_POSIX_TIME,
            "vehicle": MIN_POSIX_TIME,
            "active_periods": ((MIN_POSIX_TIME, MIN_POSIX_TIME),),
        },
        0,
    ),
    (
        {
            "header": MIN_POSIX_TIME,
            "trip_update": MIN_POSIX_TIME,
            "vehicle": MIN_POSIX_TIME,
            "active_periods": ((MIN_POSIX_TIME, MIN_POSIX_TIME), (BAD_TIME, BAD_TIME)),
        },
        2,
    ),
)


@pytest.mark.parametrize(("built", "expected"), UPSTREAM_CASES)
def test_upstream_cases(tmp_path: Path, built: dict[str, object], expected: int) -> None:
    assert len(occurrences(check(a_feed(**built), context(tmp_path, clock=NOW)))) == expected


def all_seven_sites() -> Msg:
    """One feed that reports from every site the rule has, so their order shows."""
    return message(
        entity(
            trip_update={
                "trip": {"trip_id": "1.1"},
                "timestamp": BAD_TIME,
                "stop_time_update": [
                    {
                        "stop_sequence": 4,
                        "arrival": {"time": BAD_TIME},
                        "departure": {"time": BAD_TIME},
                    }
                ],
            },
            vehicle={"vehicle": {"id": "V1"}, "timestamp": BAD_TIME},
            alert={"active_period": [{"start": BAD_TIME, "end": BAD_TIME}]},
        ),
        timestamp=BAD_TIME,
    )


def test_all_seven_prefixes_in_upstreams_order(tmp_path: Path) -> None:
    """`:104`, `:156`, `:191`, `:224`, `:283`, `:351` and `:356`.

    The two stop_time_update prefixes use the loop's own `stopDescription`
    (`:179`), which opens with a space and is **not**
    `GtfsUtils.getStopTimeUpdateId`; the difference is invisible until the two
    are concatenated onto a trip id.
    """
    assert prefixes(check(all_seven_sites(), context(tmp_path, clock=NOW))) == [
        "header.timestamp",
        f"trip_id 1.1 timestamp {BAD_TIME}",
        f"trip_id 1.1 stop_sequence 4 arrival_time {BAD_TIME}",
        f"trip_id 1.1 stop_sequence 4 departure_time {BAD_TIME}",
        f"vehicle_id V1 timestamp {BAD_TIME}",
        f"alert in entity {ENTITY_ID} active_period.start {BAD_TIME}",
        f"alert in entity {ENTITY_ID} active_period.end {BAD_TIME}",
    ]


def test_every_occurrence_says_where_it_came_from(tmp_path: Path) -> None:
    """Ours, and modern-mode only. Seven sites and seven distinct paths, which
    is the whole reason a walk attaches a context a rule cannot rebuild."""
    found = occurrences(check(all_seven_sites(), context(tmp_path, clock=NOW)))

    assert [one.context[ENTITY_PATH_KEY] for one in found] == [
        "header",
        "entity[0].trip_update",
        "entity[0].trip_update.stop_time_update[0]",
        "entity[0].trip_update.stop_time_update[0]",
        "entity[0].vehicle",
        "entity[0].alert.active_period[0]",
        "entity[0].alert.active_period[0]",
    ]
    assert {one.rule_id for one in found} == {RULE_ID}


def test_a_stop_time_update_with_neither_stop_field_names_a_bare_stop_id(
    tmp_path: Path,
) -> None:
    """`:179`'s `else` arm reads `getStopId()` unguarded, so the description is
    `" stop_id "` with a trailing space. Upstream's own `testE022` builds exactly
    this shape, which is how the text reaches a real report."""
    feed = message(
        entity(
            trip_update={
                "trip": {"trip_id": "1.1"},
                "timestamp": MIN_POSIX_TIME,
                "stop_time_update": [{"arrival": {"time": BAD_TIME}}],
            }
        ),
        timestamp=MIN_POSIX_TIME,
    )

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == [
        f"trip_id 1.1 stop_id  arrival_time {BAD_TIME}"
    ]


def test_a_stop_time_event_carrying_only_a_delay_is_not_checked(tmp_path: Path) -> None:
    """`hasArrival() && arrival.hasTime()` (`:184-185`), both halves. A delay-only
    event would otherwise read as time 0 and report as not POSIX."""
    feed = message(
        entity(
            trip_update={
                "trip": {"trip_id": "1.1"},
                "timestamp": MIN_POSIX_TIME,
                "stop_time_update": [{"stop_id": "S1", "arrival": {"delay": 30}}],
            }
        ),
        timestamp=MIN_POSIX_TIME,
    )

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == []


def test_an_absent_active_period_bound_is_not_checked(tmp_path: Path) -> None:
    """`hasStart()` and `hasEnd()` (`:349`, `:354`). An open-ended alert period
    is legal, and an absent bound reading as 0 would fail the window."""
    feed = message(
        entity(alert={"active_period": [{"start": MIN_POSIX_TIME}]}), timestamp=MIN_POSIX_TIME
    )

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == []


def test_an_absent_entity_timestamp_is_w001_and_never_e001(tmp_path: Path) -> None:
    """Both entity sites live inside the `else` of `timestamp == 0` (`:146`,
    `:272`), so an unstamped entity is warned about once and not reported as a
    timestamp of 0 outside the window."""
    feed = message(entity(trip_update={"trip": {}}, vehicle={}), timestamp=MIN_POSIX_TIME)

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == []


@pytest.mark.parametrize("timestamp", [MIN_POSIX_TIME, MAX_POSIX_TIME])
def test_both_ends_of_the_window_are_inclusive(tmp_path: Path, timestamp: int) -> None:
    """`isPosix` is `>=` and `<=` (`TimestampUtils.java:54-56`)."""
    assert prefixes(check(a_feed(timestamp, timestamp, timestamp), context(tmp_path))) == []


@pytest.mark.parametrize("timestamp", [MIN_POSIX_TIME - 1, MAX_POSIX_TIME + 1])
def test_one_second_outside_either_end_reports(tmp_path: Path, timestamp: int) -> None:
    found = prefixes(check(a_feed(timestamp, MIN_POSIX_TIME, MIN_POSIX_TIME), context(tmp_path)))

    assert found == ["header.timestamp"]
