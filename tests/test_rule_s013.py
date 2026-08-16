"""S013: a DUPLICATED trip missing one of the three `TripProperties` fields.

The proto writes one sentence three times, once on `trip_id`, once on
`start_date` and once on `start_time`, and S013 takes its first half while S014
takes its second. The verdict file records both against all three clauses as
`rule_in_part`, which is why the two rules quote the same text.

One occurrence per missing field, because the sentence is per field: a producer
told only that "the trip_properties are wrong" has to guess which.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s013 import check
from gtfs_rt_validator.rules.spec.s014 import check as s014
from specfixtures import context, entity, message, prefixes

TRIP = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]

COMPLETE = {"trip_id": "T1-copy", "start_date": "20260814", "start_time": "10:00:00"}


def trip_update(properties: dict[str, object] | None = None, relationship: str = "DUPLICATED"):
    built: dict[str, object] = {
        "trip": {"trip_id": "T1", "schedule_relationship": TRIP[relationship]}
    }
    if properties is not None:
        built["trip_properties"] = properties
    return built


def run(*entities):
    return check(message(*entities), context())


def test_all_three_present_is_what_the_clause_asks_for():
    assert prefixes(run(entity(trip_update=trip_update(COMPLETE)))) == []


def test_a_missing_start_time_is_reported():
    found = run(entity(trip_update=trip_update({"trip_id": "X", "start_date": "20260814"})))

    assert prefixes(found) == [
        "trip_id T1 is DUPLICATED and trip_properties.start_time is required"
    ]


def test_no_trip_properties_at_all_reports_all_three_in_declaration_order():
    found = run(entity(trip_update=trip_update()))

    assert prefixes(found) == [
        "trip_id T1 is DUPLICATED and trip_properties.trip_id is required",
        "trip_id T1 is DUPLICATED and trip_properties.start_date is required",
        "trip_id T1 is DUPLICATED and trip_properties.start_time is required",
    ]


def test_an_empty_trip_properties_is_the_same_as_none():
    assert len(run(entity(trip_update=trip_update({})))) == 3


def test_a_trip_that_is_not_duplicated_has_no_antecedent():
    assert prefixes(run(entity(trip_update=trip_update(relationship="SCHEDULED")))) == []


def test_a_vehicle_position_carries_no_trip_properties_field():
    """`TripProperties` hangs off `TripUpdate` and nothing else, so a
    DUPLICATED VehiclePosition is S020's business rather than this rule's."""
    found = run(
        entity(vehicle={"trip": {"trip_id": "T1", "schedule_relationship": TRIP["DUPLICATED"]}})
    )

    assert prefixes(found) == []


def test_the_occurrence_locates_the_properties_and_carries_this_rules_id():
    found = run(entity(trip_update=trip_update({"trip_id": "X", "start_date": "20260814"})))

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.trip_properties"
    ]
    assert [occurrence.rule_id for occurrence in found] == ["S013"]


def test_the_two_halves_of_the_sentence_never_fire_on_one_field():
    """S013 needs DUPLICATED and S014 needs anything else, so a feed reaching
    both on one trip is not expressible."""
    duplicated = message(entity(trip_update=trip_update({"trip_id": "X"})))
    scheduled = message(entity(trip_update=trip_update({"trip_id": "X"}, relationship="SCHEDULED")))

    assert len(list(check(duplicated, context()))) == 2
    assert list(s014(duplicated, context())) == []
    assert list(check(scheduled, context())) == []
    assert len(list(s014(scheduled, context()))) == 1
