"""P005: a VehiclePosition timestamp more than 90 seconds behind the run's clock.

The one rule in the tier whose declared absence of any upstream overlap the jar
confirms, rather than only a reading of the Java. Measured, one invocation per
case:

| entity age | jar |
|---|---|
| 0 | nothing |
| 90 | nothing |
| 91 | nothing |
| 100 | nothing |
| entity timestamp ahead of the header | E012 |

W008 is the header, E012 is the entity against the header and E050 is the
future. Nothing in the 56 compares an entity timestamp against the clock at any
age, which is what makes this rule the document's example in the flesh: a fresh
header does not make stale entities fresh.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.rules._shared.times import MAX_POSIX_TIME, MIN_POSIX_TIME
from gtfs_rt_validator.rules.practice.p005 import check
from specfixtures import READING, context, entity, message, prefixes

CLOCK = READING.millis // 1000


def vehicle(timestamp: int | None, **overrides: object) -> dict[str, object]:
    built: dict[str, object] = {
        "trip": {"trip_id": "T1"},
        "vehicle": {"id": "1"},
        "position": {"latitude": 27.95, "longitude": -82.45},
    }
    if timestamp is not None:
        built["timestamp"] = timestamp
    built.update(overrides)
    return built


def run(*vehicles: dict[str, object]):
    entities = [entity(f"e{index}", vehicle=one) for index, one in enumerate(vehicles)]
    return check(message(*entities, timestamp=CLOCK), context())


def stale(age: int) -> str:
    return (
        f"vehicle_id 1 trip_id T1 timestamp {CLOCK - age} is {age} seconds old, "
        "more than the 90 seconds the practice allows"
    )


@pytest.mark.parametrize("age", [91, 100, 600])
def test_a_stale_vehicle_timestamp_is_reported(age):
    assert prefixes(run(vehicle(CLOCK - age))) == [stale(age)]


@pytest.mark.parametrize("age", [0, 1, 89, 90])
def test_an_age_the_document_allows_is_silent(age):
    """90 is the boundary and the sentence excludes it: "should not be older
    than 90 seconds" is satisfied by exactly 90."""
    assert prefixes(run(vehicle(CLOCK - age))) == []


def test_a_timestamp_in_the_future_is_e050s_and_not_this_rules():
    assert prefixes(run(vehicle(CLOCK + 600))) == []


def test_an_absent_timestamp_is_w001s_and_not_this_rules():
    """W001 is the rule for a VehiclePosition that states no timestamp, and it
    fires on a zero one too, because upstream reads the field with no `has`."""
    assert prefixes(run(vehicle(None), vehicle(0))) == []


@pytest.mark.parametrize("timestamp", [1, MIN_POSIX_TIME - 1, MAX_POSIX_TIME + 1])
def test_a_timestamp_outside_the_posix_window_is_e001s(timestamp):
    """E001 already reports it, and it stops upstream's ladder there. Firing
    here as well would put a P occurrence beside an upstream one this rule does
    not declare, for a value that is not a time at all."""
    assert prefixes(run(vehicle(timestamp))) == []


def test_a_trip_update_timestamp_is_not_this_rules_business():
    """The sentence names VehiclePositions. `:61`'s TripUpdate.timestamp
    sentence is rejected under R3, so nothing here reads one."""
    found = check(
        message(
            entity("e0", trip_update={"trip": {"trip_id": "T1"}, "timestamp": CLOCK - 600}),
            timestamp=CLOCK,
        ),
        context(),
    )

    assert prefixes(found) == []


def test_every_stale_vehicle_in_a_message_is_reported_in_feed_order():
    found = run(vehicle(CLOCK - 100), vehicle(CLOCK), vehicle(CLOCK - 200))

    assert prefixes(found) == [stale(100), stale(200)]


def test_the_occurrence_names_the_entity_it_came_from():
    (found,) = list(run(vehicle(CLOCK), vehicle(CLOCK - 100)))

    assert found.context == {
        "entityPath": "entity[1].vehicle",
        "ageSeconds": 100,
        "timestamp": CLOCK - 100,
    }
