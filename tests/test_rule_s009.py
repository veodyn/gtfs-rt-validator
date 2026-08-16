"""S009: UNSCHEDULED stop_time_updates under a descriptor that is not UNSCHEDULED.

S010 is the other direction and they are two rules rather than one, because
they fire on different feeds and cite different sentences at different lines.
The last test here is the one that shows they cannot both fire on one trip: the
descriptor either is UNSCHEDULED or is not.

One occurrence per trip, because the defect the sentence names is the
descriptor's, however many updates make it visible.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s009 import check
from gtfs_rt_validator.rules.spec.s010 import check as s010
from specfixtures import context, entity, message, prefixes

TRIP = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]
STOP_TIME = SCHEMA.enums["TripUpdate.StopTimeUpdate.ScheduleRelationship"]


def update(relationship: str | None = None) -> dict[str, object]:
    built: dict[str, object] = {"stop_id": "S1"}
    if relationship is not None:
        built["schedule_relationship"] = STOP_TIME[relationship]
    return built


def trip_update(*updates: dict[str, object], relationship: str | None = None) -> dict[str, object]:
    trip: dict[str, object] = {"trip_id": "T1"}
    if relationship is not None:
        trip["schedule_relationship"] = TRIP[relationship]
    return {"trip": trip, "stop_time_update": list(updates)}


def run(*entities):
    return check(message(*entities), context())


def test_both_ends_unscheduled_is_what_the_clause_asks_for():
    found = run(entity(trip_update=trip_update(update("UNSCHEDULED"), relationship="UNSCHEDULED")))

    assert prefixes(found) == []


def test_an_unscheduled_update_under_a_scheduled_descriptor_is_reported():
    found = run(entity(trip_update=trip_update(update("UNSCHEDULED"))))

    assert prefixes(found) == [
        "trip_id T1 has UNSCHEDULED stop_time_updates but the trip is SCHEDULED"
    ]


def test_it_reports_once_per_trip_however_many_updates_are_unscheduled():
    found = run(entity(trip_update=trip_update(update("UNSCHEDULED"), update("UNSCHEDULED"))))

    assert len(found) == 1


def test_a_canceled_descriptor_is_reported_and_named():
    found = run(entity(trip_update=trip_update(update("UNSCHEDULED"), relationship="CANCELED")))

    assert prefixes(found) == [
        "trip_id T1 has UNSCHEDULED stop_time_updates but the trip is CANCELED"
    ]


def test_no_unscheduled_update_is_not_a_finding():
    found = run(entity(trip_update=trip_update(update(), update("SKIPPED"))))

    assert prefixes(found) == []


def test_a_trip_with_no_updates_at_all_is_not_a_finding():
    assert prefixes(run(entity(trip_update=trip_update()))) == []


def test_the_occurrence_names_the_trip_and_carries_this_rules_id():
    found = run(entity(trip_update=trip_update(update("UNSCHEDULED"))))

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.trip"
    ]
    assert [occurrence.rule_id for occurrence in found] == ["S009"]


def test_the_two_directions_of_the_triangle_never_fire_on_one_trip():
    """S009 needs a descriptor that is not UNSCHEDULED and S010 needs one that
    is, so a feed reaching both is not expressible."""
    mixed = message(
        entity(trip_update=trip_update(update("UNSCHEDULED"), update(), relationship="UNSCHEDULED"))
    )

    assert prefixes(check(mixed, context())) == []
    assert len(list(s010(mixed, context()))) == 1
