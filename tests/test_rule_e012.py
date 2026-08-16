"""E012, an entity timestamp ahead of the header timestamp.

`testE012` (`TimestampValidatorTest.java:427-524`) is upstream's, ported stage by
stage from the checkout at `jar-build/upstream/`. Upstream asserts counts only;
everything below `UPSTREAM_CASES` is ours.

Its five stages pin the shape of the comparison: strictly greater, so an entity
equal to the header passes, and each of the two sites counted separately.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.times import MAX_POSIX_TIME, MIN_POSIX_TIME
from gtfs_rt_validator.rules.upstream.e012 import RULE_ID, check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from rulefixtures import ENTITY_ID, context, entity, message, occurrences, prefixes

NOW = Reading(MIN_POSIX_TIME * 1000, ClockSource.FIXED)


def a_feed(header: int, trip_update: int, vehicle: int, vehicle_id: str | None = None) -> Msg:
    """`testE012`'s entity. Upstream never sets a VehicleDescriptor here, so the
    prefix it produces carries two spaces; `vehicle_id` puts one in for the
    tests that are about the text rather than the count."""
    position: dict[str, object] = {"timestamp": vehicle}
    if vehicle_id is not None:
        position["vehicle"] = {"id": vehicle_id}
    return message(
        entity(trip_update={"trip": {}, "timestamp": trip_update}, vehicle=position),
        timestamp=header,
    )


#: `testE012` in order: header, TripUpdate and VehiclePosition timestamps, then
#: the count upstream asserts.
UPSTREAM_CASES = (
    (MIN_POSIX_TIME + 1, MIN_POSIX_TIME, MIN_POSIX_TIME, 0),
    (MIN_POSIX_TIME, MIN_POSIX_TIME, MIN_POSIX_TIME, 0),
    (MIN_POSIX_TIME, MIN_POSIX_TIME, MIN_POSIX_TIME + 1, 1),
    (MIN_POSIX_TIME, MIN_POSIX_TIME + 1, MIN_POSIX_TIME, 1),
    (MIN_POSIX_TIME, MIN_POSIX_TIME + 1, MIN_POSIX_TIME + 1, 2),
)


@pytest.mark.parametrize(("header", "trip_update", "vehicle", "expected"), UPSTREAM_CASES)
def test_upstream_cases(
    tmp_path: Path, header: int, trip_update: int, vehicle: int, expected: int
) -> None:
    feed = a_feed(header, trip_update, vehicle)

    assert len(occurrences(check(feed, context(tmp_path, clock=NOW)))) == expected


def test_the_two_prefixes_name_the_trip_then_the_vehicle(tmp_path: Path) -> None:
    """`:152` and `:276`, and the TripUpdate is reported first because the entity
    loop reaches it first (`:138` before `:268`)."""
    feed = a_feed(MIN_POSIX_TIME, MIN_POSIX_TIME + 1, MIN_POSIX_TIME + 2, vehicle_id="V1")

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == [
        f"entity ID {ENTITY_ID} timestamp {MIN_POSIX_TIME + 1}",
        f"vehicle_id V1 timestamp {MIN_POSIX_TIME + 2}",
    ]


def test_an_absent_vehicle_descriptor_leaves_two_spaces(tmp_path: Path) -> None:
    """`"vehicle_id " + getVehicle().getId() + " timestamp "` is built with no
    presence guard (`:276`), which is upstream's text and not a bug to tidy."""
    feed = a_feed(MIN_POSIX_TIME, MIN_POSIX_TIME, MIN_POSIX_TIME + 1)

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == [
        f"vehicle_id  timestamp {MIN_POSIX_TIME + 1}"
    ]


def test_an_absent_header_timestamp_silences_both_sites(tmp_path: Path) -> None:
    """`headerTimestamp != 0` guards each site (`:150`, `:277`), so an unstamped
    header makes every entity timestamp "greater" and none of them reported."""
    feed = message(
        entity(
            trip_update={"trip": {}, "timestamp": MIN_POSIX_TIME},
            vehicle={"timestamp": MIN_POSIX_TIME},
        )
    )

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == []


def test_an_absent_entity_timestamp_is_w001_and_never_e012(tmp_path: Path) -> None:
    """Both sites live in the `else` of `timestamp == 0`, so a zero is not
    compared against the header at all."""
    feed = message(entity(trip_update={"trip": {}}, vehicle={}), timestamp=MIN_POSIX_TIME)

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == []


def test_a_non_posix_timestamp_is_still_compared(tmp_path: Path) -> None:
    """Neither site is gated on `isPosix`, and E012 is tested *before* E001 on
    the same value (`:150-156`), so a timestamp in milliseconds past the header
    reports under both ids rather than only under E001."""
    feed = a_feed(MIN_POSIX_TIME, MIN_POSIX_TIME * 1000, MIN_POSIX_TIME)

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == [
        f"entity ID {ENTITY_ID} timestamp {MIN_POSIX_TIME * 1000}"
    ]


def test_stop_time_update_times_are_not_compared_against_the_header(tmp_path: Path) -> None:
    """Only the two entity timestamps are; the stop_time_update loop has no E012
    site at all, so a trip whose stops run past the header is E022's business."""
    feed = message(
        entity(
            trip_update={
                "trip": {},
                "timestamp": MIN_POSIX_TIME,
                "stop_time_update": [
                    {"stop_id": "S1", "arrival": {"time": MAX_POSIX_TIME}},
                ],
            }
        ),
        timestamp=MIN_POSIX_TIME,
    )

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == []


def test_the_occurrences_locate_each_entity(tmp_path: Path) -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone."""
    feed = a_feed(MIN_POSIX_TIME, MIN_POSIX_TIME + 1, MIN_POSIX_TIME + 1)
    found = occurrences(check(feed, context(tmp_path, clock=NOW)))

    assert [one.context[ENTITY_PATH_KEY] for one in found] == [
        "entity[0].trip_update",
        "entity[0].vehicle",
    ]
    assert {one.rule_id for one in found} == {RULE_ID}
