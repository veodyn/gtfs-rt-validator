"""S004: `StopTimeEvent.scheduled_time` on a trip that is not NEW, REPLACEMENT
or DUPLICATED.

The clause is one sentence and both halves are in it: optional for those three
relationships, "forbidden otherwise". The field exists so a trip with no
schedule in GTFS can state one, which is why the exempt set is exactly the three
relationships that produce a trip GTFS does not already carry a schedule for.

`scheduled_time` is post-2015 and so is `NEW`, so nothing in the 56 can reach
this.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s004 import check
from specfixtures import context, entity, message, prefixes

RELATIONSHIPS = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]


def trip_update(*updates: dict[str, object], relationship: str | None = None) -> dict[str, object]:
    trip: dict[str, object] = {"trip_id": "T1"}
    if relationship is not None:
        trip["schedule_relationship"] = RELATIONSHIPS[relationship]
    return {"trip": trip, "stop_time_update": list(updates)}


def run(*entities):
    return check(message(*entities), context())


@pytest.mark.parametrize("relationship", ["NEW", "REPLACEMENT", "DUPLICATED"])
def test_the_three_relationships_the_clause_names_may_carry_it(relationship):
    found = run(
        entity(
            trip_update=trip_update(
                {"stop_id": "S1", "arrival": {"scheduled_time": 1_700_000_000}},
                relationship=relationship,
            )
        )
    )

    assert prefixes(found) == []


def test_a_scheduled_trip_carrying_it_is_reported():
    found = run(
        entity(trip_update=trip_update({"stop_id": "S1", "arrival": {"scheduled_time": 1}}))
    )

    assert prefixes(found) == [
        "trip_id T1 stop_time_update[0] arrival has scheduled_time on a SCHEDULED trip"
    ]


def test_an_absent_schedule_relationship_is_scheduled():
    """proto2's default, and the reason the walk carries `declared` beside the
    resolved value: this rule wants the value a consumer reads."""
    found = run(
        entity(
            trip_update=trip_update(
                {"stop_id": "S1", "departure": {"scheduled_time": 1}}, relationship="SCHEDULED"
            )
        )
    )

    assert prefixes(found) == [
        "trip_id T1 stop_time_update[0] departure has scheduled_time on a SCHEDULED trip"
    ]


def test_a_canceled_trip_carrying_it_is_reported_and_names_its_relationship():
    found = run(
        entity(
            trip_update=trip_update(
                {"stop_id": "S1", "arrival": {"scheduled_time": 1}}, relationship="CANCELED"
            )
        )
    )

    assert prefixes(found) == [
        "trip_id T1 stop_time_update[0] arrival has scheduled_time on a CANCELED trip"
    ]


def test_an_event_with_no_scheduled_time_is_not_a_finding():
    found = run(entity(trip_update=trip_update({"stop_id": "S1", "arrival": {"delay": 30}})))

    assert prefixes(found) == []


def test_both_events_of_one_update_report_separately_arrival_first():
    found = run(
        entity(
            trip_update=trip_update(
                {
                    "stop_id": "S1",
                    "arrival": {"scheduled_time": 1},
                    "departure": {"scheduled_time": 2},
                }
            )
        )
    )

    assert prefixes(found) == [
        "trip_id T1 stop_time_update[0] arrival has scheduled_time on a SCHEDULED trip",
        "trip_id T1 stop_time_update[0] departure has scheduled_time on a SCHEDULED trip",
    ]


def test_the_occurrence_locates_the_event_and_carries_this_rules_id():
    found = run(
        entity(
            trip_update=trip_update(
                {"stop_id": "S1"}, {"stop_id": "S2", "departure": {"scheduled_time": 1}}
            )
        )
    )

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.stop_time_update[1].departure"
    ]
    assert [occurrence.rule_id for occurrence in found] == ["S004"]


def test_a_vehicle_position_has_no_stop_time_updates_to_check():
    found = run(entity(vehicle={"trip": {"trip_id": "T1"}}))

    assert prefixes(found) == []
