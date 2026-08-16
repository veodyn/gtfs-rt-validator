"""`TimestampValidator`'s one pass, as a walk eleven rule modules read.

What is asserted here is the part no single rule test can see: that the header
block runs before the entity loop, that one entity emits its TripUpdate half
then its VehiclePosition half then its Alert half, and that a stop_time_update's
E022 comparisons come out in the Java's own order. Each rule's counts and
occurrence text are pinned in its own test file, against upstream's
`TimestampValidatorTest`.

Nothing below is ported: upstream has no test for emission order, because its
validator builds eleven lists and never interleaves them. The order still
matters here, because `--compat` writes one group per rule in registration
order and the occurrences inside a group in the order the loop produced them.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.times import MIN_POSIX_TIME
from gtfs_rt_validator.rules._shared.walk_timestamp import timestamps
from gtfs_rt_validator.rules._shared.walks import walk_events
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from rulefixtures import ENTITY_ID, context, entity, message

#: `TimestampValidatorTest`'s own "current time", `MIN_POSIX_TIME` in millis.
NOW = Reading(MIN_POSIX_TIME * 1000, ClockSource.FIXED)

#: A timestamp in milliseconds where seconds were meant, upstream's `BAD_TIME`.
BAD_TIME = MIN_POSIX_TIME * 1000


def events(msg, ctx):
    return list(walk_events(timestamps, msg, ctx))


def test_the_header_block_is_emitted_before_the_first_entity(tmp_path: Path) -> None:
    """`:86-135` runs to completion before `:137` opens the loop, so a header
    finding precedes every entity finding whatever their rule ids are."""
    msg = message(
        entity(trip_update={"trip": {}}, vehicle={"vehicle": {"id": "V1"}}),
        timestamp=BAD_TIME,
    )

    found = events(msg, context(tmp_path, clock=NOW))

    assert [(e.rule_id, e.prefix) for e in found] == [
        ("E001", "header.timestamp"),
        ("W001", "entity ID TEST_ENTITY"),
        ("W001", "vehicle_id V1"),
    ]


def test_one_entity_emits_trip_update_then_vehicle_then_alert(tmp_path: Path) -> None:
    """The three halves at `:138`, `:268` and `:297`, in that order.

    Each entity half also shows E012 emitted before E001 on the same timestamp
    (`:150-156` and `:277-283`), which is what makes a value that is both past
    the header and not POSIX report twice with one prefix.
    """
    msg = message(
        entity(
            trip_update={"trip": {}, "timestamp": BAD_TIME},
            vehicle={"vehicle": {"id": "V1"}, "timestamp": BAD_TIME},
            alert={"active_period": [{"start": BAD_TIME}]},
        ),
        timestamp=MIN_POSIX_TIME,
    )

    found = events(msg, context(tmp_path, clock=NOW))

    trip = f"entity ID {ENTITY_ID} timestamp {BAD_TIME}"
    vehicle = f"vehicle_id V1 timestamp {BAD_TIME}"
    assert [(e.rule_id, e.prefix) for e in found] == [
        ("E012", trip),
        ("E001", trip),
        ("E012", vehicle),
        ("E001", vehicle),
        ("E001", f"alert in entity {ENTITY_ID} active_period.start {BAD_TIME}"),
    ]


def test_the_entity_path_locates_every_site_the_walk_reports_from(tmp_path: Path) -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone. A rule
    inside a shared loop cannot rebuild the position the loop was standing at,
    which is why `Event` carries a context at all."""
    msg = message(
        entity(
            trip_update={
                "trip": {},
                "timestamp": BAD_TIME,
                "stop_time_update": [{"stop_id": "S1", "arrival": {"time": BAD_TIME}}],
            },
            vehicle={"vehicle": {"id": "V1"}, "timestamp": BAD_TIME},
            alert={"active_period": [{"start": BAD_TIME}]},
        ),
        timestamp=BAD_TIME,
    )

    found = events(msg, context(tmp_path, clock=NOW))

    assert [e.context[ENTITY_PATH_KEY] for e in found] == [
        "header",
        "entity[0].trip_update",
        "entity[0].trip_update.stop_time_update[0]",
        "entity[0].vehicle",
        "entity[0].alert.active_period[0]",
    ]


def test_a_stop_time_update_emits_its_four_arrival_cases_before_its_departure_cases(
    tmp_path: Path,
) -> None:
    """`:193-213` then `:226-245`, eight independent `if`s. The four that fire
    here are arrival-less-than, arrival-equal-to, departure-less-than and
    departure-equal-to, and E025 is emitted last of all (`:246`)."""
    at_min = {"time": MIN_POSIX_TIME}
    stop_times = [
        {"stop_sequence": 1, "arrival": at_min, "departure": at_min},
        {"stop_sequence": 2, "arrival": at_min, "departure": at_min},
    ]
    msg = message(
        entity(
            trip_update={
                "trip": {},
                "timestamp": MIN_POSIX_TIME,
                "stop_time_update": stop_times,
            }
        ),
        timestamp=MIN_POSIX_TIME,
    )

    found = [e.prefix for e in events(msg, context(tmp_path, clock=NOW)) if e.rule_id == "E022"]

    def equal_to(field: str, previous_field: str) -> str:
        moment = f"19:00:00 ({MIN_POSIX_TIME})"
        return (
            f"entity ID {ENTITY_ID} stop_sequence 2 {field} {moment} "
            f"is equal to previous stop {previous_field} {moment}"
        )

    assert found == [
        equal_to("arrival_time", "arrival_time"),
        equal_to("arrival_time", "departure_time"),
        equal_to("departure_time", "departure_time"),
        equal_to("departure_time", "arrival_time"),
    ]


def test_the_walk_runs_once_for_all_eleven_rules(tmp_path: Path) -> None:
    """`walks.walk_events` memoises on `ctx.memo`; this is the entry that
    proves the eleven rules of this validator share one pass."""
    msg = message(entity(trip_update={"trip": {}}), timestamp=MIN_POSIX_TIME)
    ctx = context(tmp_path, clock=NOW)

    events(msg, ctx)

    assert list(ctx.memo) == ["walk:gtfs_rt_validator.rules._shared.walk_timestamp.timestamps"]
