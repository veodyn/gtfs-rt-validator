"""S014: a `TripProperties` field populated on a trip that is not DUPLICATED.

The second half of S013's sentence, "otherwise this field must not be populated
and will be ignored by consumers". The consequence is in the clause: a consumer
throws the value away, so a producer who wrote it has silently lost whatever it
was for.

`shape_id` and `trip_headsign` are also `TripProperties` fields and are **not**
in scope: the sentence is written on `trip_id`, `start_date` and `start_time`
only, and `shape_id`'s own comment describes a detour on an ordinary scheduled
trip, which is the opposite of forbidden.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s014 import check
from specfixtures import context, entity, message, prefixes

TRIP = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]


def trip_update(properties: dict[str, object] | None = None, relationship: str | None = None):
    trip: dict[str, object] = {"trip_id": "T1"}
    if relationship is not None:
        trip["schedule_relationship"] = TRIP[relationship]
    built: dict[str, object] = {"trip": trip}
    if properties is not None:
        built["trip_properties"] = properties
    return built


def run(*entities):
    return check(message(*entities), context())


def test_a_scheduled_trip_with_no_trip_properties_is_not_a_finding():
    assert prefixes(run(entity(trip_update=trip_update()))) == []


def test_a_duplicated_trip_may_populate_all_three():
    found = run(
        entity(
            trip_update=trip_update(
                {"trip_id": "X", "start_date": "20260814", "start_time": "10:00:00"},
                relationship="DUPLICATED",
            )
        )
    )

    assert prefixes(found) == []


def test_a_scheduled_trip_populating_trip_id_is_reported():
    found = run(entity(trip_update=trip_update({"trip_id": "X"})))

    assert prefixes(found) == [
        "trip_id T1 is SCHEDULED and trip_properties.trip_id must not be populated"
    ]


def test_a_new_trip_populating_all_three_reports_each_in_declaration_order():
    found = run(
        entity(
            trip_update=trip_update(
                {"start_time": "10:00:00", "trip_id": "X", "start_date": "20260814"},
                relationship="NEW",
            )
        )
    )

    assert prefixes(found) == [
        "trip_id T1 is NEW and trip_properties.trip_id must not be populated",
        "trip_id T1 is NEW and trip_properties.start_date must not be populated",
        "trip_id T1 is NEW and trip_properties.start_time must not be populated",
    ]


def test_shape_id_is_not_one_of_the_three():
    """The sentence is written on `trip_id`, `start_date` and `start_time`.
    `shape_id`'s own comment describes a detour on a scheduled trip."""
    found = run(entity(trip_update=trip_update({"shape_id": "SH2"})))

    assert prefixes(found) == []


def test_the_occurrence_locates_the_properties_and_carries_this_rules_id():
    found = run(entity(trip_update=trip_update({"start_date": "20260814"})))

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.trip_properties"
    ]
    assert [occurrence.rule_id for occurrence in found] == ["S014"]
