"""S017: `TripUpdate.delay` on a NEW trip.

The clause says delay is for a prediction "given relative to some existing
schedule in GTFS", and NEW is the one relationship the proto defines as having
none: `:900` calls it "An extra trip unrelated to any existing trips". Every
other member either is the GTFS trip (SCHEDULED, CANCELED, DELETED,
UNSCHEDULED), copies one (DUPLICATED, and `:873` says which via
`TripUpdate.TripDescriptor.trip_id`) or replaces one (REPLACEMENT).

Not E046, which compares a *stop_time_update's* delay against `stop_times.txt`.
This one is about the trip-level field and never opens the static feed.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s017 import check
from specfixtures import context, entity, message, prefixes

TRIP = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]


def trip_update(delay: int | None = None, relationship: str | None = None):
    trip: dict[str, object] = {"trip_id": "T1"}
    if relationship is not None:
        trip["schedule_relationship"] = TRIP[relationship]
    built: dict[str, object] = {"trip": trip}
    if delay is not None:
        built["delay"] = delay
    return built


def run(*entities):
    return check(message(*entities), context())


def test_a_delay_on_a_scheduled_trip_is_what_the_clause_permits():
    assert prefixes(run(entity(trip_update=trip_update(30)))) == []


@pytest.mark.parametrize("relationship", ["DUPLICATED", "REPLACEMENT", "UNSCHEDULED", "CANCELED"])
def test_every_other_relationship_relates_to_an_existing_schedule(relationship):
    assert prefixes(run(entity(trip_update=trip_update(30, relationship)))) == []


def test_a_delay_on_a_new_trip_is_reported():
    found = run(entity(trip_update=trip_update(30, "NEW")))

    assert prefixes(found) == ["trip_id T1 has delay 30 on a NEW trip"]


def test_a_delay_of_zero_is_still_a_delay():
    """Presence, not truth: 0 means "exactly on time" relative to a schedule
    the NEW trip does not have."""
    found = run(entity(trip_update=trip_update(0, "NEW")))

    assert prefixes(found) == ["trip_id T1 has delay 0 on a NEW trip"]


def test_a_new_trip_with_no_delay_is_not_a_finding():
    assert prefixes(run(entity(trip_update=trip_update(relationship="NEW")))) == []


def test_it_reports_once_per_trip_rather_than_once_per_stop():
    found = run(
        entity(
            trip_update={
                "trip": {"trip_id": "T1", "schedule_relationship": TRIP["NEW"]},
                "delay": 30,
                "stop_time_update": [{"stop_id": "S1"}, {"stop_id": "S2"}],
            }
        )
    )

    assert len(found) == 1


def test_the_occurrence_names_the_trip_and_carries_this_rules_id():
    found = run(entity(trip_update=trip_update(30, "NEW")))

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.trip"
    ]
    assert [occurrence.rule_id for occurrence in found] == ["S017"]
