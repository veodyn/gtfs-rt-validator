"""P009: a NEW trip that states no `TripProperties.trip_headsign`.

The clause carries two halves and this rule enforces the first. The NEW half is
unconditional, so it is checkable; the REPLACEMENT half is conditioned on "if
the trip is diverted", which no field of a feed states, so the tests below
assert that a REPLACEMENT trip with no headsign is **silent**. That silence is
the narrowing, and it is the assertion that would fail first if somebody
widened the rule to the whole sentence.

`NEW` and `trip_properties` are both post-2015, so a 2015 decode drops the
relationship and the whole submessage: the jar sees a SCHEDULED trip with
unknown fields, and nothing in the 56 can reach this.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.practice.p009 import check
from specfixtures import context, entity, message, prefixes

RELATIONSHIPS = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]

REPORTED = "trip_id T1 is NEW and trip_properties.trip_headsign is not provided"


def trip_update(relationship: str = "NEW", **properties: object) -> dict[str, object]:
    trip = {"trip_id": "T1", "schedule_relationship": RELATIONSHIPS[relationship]}
    built: dict[str, object] = {"trip": trip}
    if properties:
        built["trip_properties"] = dict(properties)
    return built


def run(*entities):
    return check(message(*entities), context())


def test_a_new_trip_with_no_headsign_is_reported():
    assert prefixes(run(entity(trip_update=trip_update()))) == [REPORTED]


def test_a_new_trip_stating_its_headsign_is_silent():
    """The conformant twin. Everything else about the feed is identical."""
    found = run(entity(trip_update=trip_update(trip_headsign="Downtown")))

    assert prefixes(found) == []


def test_trip_properties_present_but_carrying_other_fields_is_still_a_finding():
    """An absent submessage and a submessage with no headsign in it are the same
    failure, which is why the rule tests the field rather than the message."""
    found = run(entity(trip_update=trip_update(trip_id="T1-copy")))

    assert prefixes(found) == [REPORTED]


def test_an_empty_headsign_string_counts_as_provided():
    """proto2 presence, not truthiness. A producer that states the headsign as
    the empty string has stated it, and this rule is not the one with an opinion
    about that."""
    assert prefixes(run(entity(trip_update=trip_update(trip_headsign="")))) == []


@pytest.mark.parametrize(
    "relationship", ["SCHEDULED", "ADDED", "UNSCHEDULED", "CANCELED", "REPLACEMENT", "DUPLICATED"]
)
def test_only_new_is_in_scope(relationship):
    """REPLACEMENT is in the list on purpose: the clause's second half asks for a
    headsign on a *diverted* REPLACEMENT trip, and diversion is not observable,
    so the rule drops that half rather than guessing."""
    assert prefixes(run(entity(trip_update=trip_update(relationship)))) == []


def test_an_absent_schedule_relationship_is_scheduled_and_out_of_scope():
    found = run(entity(trip_update={"trip": {"trip_id": "T1"}}))

    assert prefixes(found) == []


def test_a_vehicle_position_carries_no_trip_properties():
    """`TripProperties` hangs off `TripUpdate` alone, so a NEW VehiclePosition
    has no field this rule could be about."""
    found = run(
        entity(vehicle={"trip": {"trip_id": "T1", "schedule_relationship": RELATIONSHIPS["NEW"]}})
    )

    assert prefixes(found) == []


def test_an_alert_selector_is_not_a_trip_update():
    found = run(
        entity(
            alert={
                "informed_entity": [
                    {"trip": {"trip_id": "T1", "schedule_relationship": RELATIONSHIPS["NEW"]}}
                ]
            }
        )
    )

    assert prefixes(found) == []


def test_the_occurrence_locates_the_properties_and_carries_this_rules_id():
    found = run(entity(trip_update=trip_update()))

    assert [found_one.context["entityPath"] for found_one in found] == [
        "entity[0].trip_update.trip_properties"
    ]
    assert [found_one.rule_id for found_one in found] == ["P009"]
    assert [found_one.context["tripId"] for found_one in found] == ["T1"]


def test_two_new_trips_are_reported_in_feed_order():
    found = run(
        entity("A", trip_update=trip_update()),
        entity("B", trip_update=trip_update(trip_headsign="Uptown")),
        entity("C", trip_update=trip_update()),
    )

    assert [found_one.context["entityPath"] for found_one in found] == [
        "entity[0].trip_update.trip_properties",
        "entity[2].trip_update.trip_properties",
    ]
