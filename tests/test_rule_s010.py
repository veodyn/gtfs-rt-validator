"""S010: a stop_time_update that is not UNSCHEDULED under a trip that is.

The other direction of S009's triangle, and the counting is the other way round
too: once per offending update, because "all StopTimeUpdates" makes each one the
defect, where S009's descriptor is a single defect however many updates expose
it.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s010 import check
from specfixtures import context, entity, message, prefixes

TRIP = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]
STOP_TIME = SCHEMA.enums["TripUpdate.StopTimeUpdate.ScheduleRelationship"]


def update(relationship: str | None = None) -> dict[str, object]:
    built: dict[str, object] = {"stop_id": "S1"}
    if relationship is not None:
        built["schedule_relationship"] = STOP_TIME[relationship]
    return built


def trip_update(
    *updates: dict[str, object], relationship: str = "UNSCHEDULED"
) -> dict[str, object]:
    return {
        "trip": {"trip_id": "T1", "schedule_relationship": TRIP[relationship]},
        "stop_time_update": list(updates),
    }


def run(*entities):
    return check(message(*entities), context())


def test_every_update_unscheduled_is_what_the_clause_asks_for():
    found = run(entity(trip_update=trip_update(update("UNSCHEDULED"), update("UNSCHEDULED"))))

    assert prefixes(found) == []


def test_an_update_that_declares_nothing_is_scheduled_and_is_reported():
    """proto2's default is the value the clause forbids, so omitting the field
    under an UNSCHEDULED trip is exactly the mistake."""
    found = run(entity(trip_update=trip_update(update())))

    assert prefixes(found) == ["trip_id T1 stop_time_update[0] is SCHEDULED on an UNSCHEDULED trip"]


def test_a_skipped_update_is_reported_and_named():
    found = run(entity(trip_update=trip_update(update("SKIPPED"))))

    assert prefixes(found) == ["trip_id T1 stop_time_update[0] is SKIPPED on an UNSCHEDULED trip"]


def test_each_offending_update_reports_once():
    found = run(entity(trip_update=trip_update(update("UNSCHEDULED"), update(), update("NO_DATA"))))

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.stop_time_update[1]",
        "entity[0].trip_update.stop_time_update[2]",
    ]


def test_a_trip_that_is_not_unscheduled_is_not_in_scope():
    found = run(entity(trip_update=trip_update(update(), relationship="SCHEDULED")))

    assert prefixes(found) == []


def test_a_trip_with_no_updates_at_all_is_not_a_finding():
    assert prefixes(run(entity(trip_update=trip_update()))) == []


def test_every_occurrence_carries_this_rules_id():
    assert [o.rule_id for o in run(entity(trip_update=trip_update(update())))] == ["S010"]
