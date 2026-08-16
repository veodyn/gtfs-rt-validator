"""S024: the deprecated `ADDED` relationship, read off the schema.

The plan says S024 has to compare a member name because the generator drops
`[deprecated = true]` on enum members. That is no longer true: `Schema` carries
`deprecated_enum_values` and `_shared/schedule_relationship.py` exposes
`DEPRECATED_TRIP_RELATIONSHIPS`, so the fact reaches the rule through the pin.
The first test below asserts that the pin's answer is the one member the proto
marks, which is what keeps the rule from passing over an empty set.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.schedule_relationship import (
    ADDED,
    DEPRECATED_TRIP_RELATIONSHIPS,
    DUPLICATED,
    NEW,
    SCHEDULED,
)
from gtfs_rt_validator.rules.spec.s024 import check
from specfixtures import context, entity, message

#: The enum numbers the encoder needs, since a fixture writes the wire value.
NUMBERS = {SCHEDULED: 0, ADDED: 1, DUPLICATED: 6, NEW: 8}


def found(**trip):
    feed = message(entity(trip_update={"trip": dict(trip)}))
    return list(check(feed, context()) or ())


def prefixes(**trip):
    return [occurrence.prefix for occurrence in found(**trip)]


def test_the_pin_marks_exactly_one_relationship_deprecated():
    """`ADDED = 1 [deprecated = true]` at proto line 856, and nothing else. A
    rule reading an empty set would pass every test below by firing never."""
    assert set(DEPRECATED_TRIP_RELATIONSHIPS) == {ADDED}


def test_a_trip_declared_added_reports():
    assert prefixes(trip_id="T1", schedule_relationship=NUMBERS[ADDED]) == [
        "trip_id T1 uses schedule_relationship ADDED, which this pin deprecates"
    ]


def test_the_occurrence_locates_the_descriptor():
    (occurrence,) = found(trip_id="T1", schedule_relationship=NUMBERS[ADDED])

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].trip_update.trip"


def test_a_descriptor_with_no_trip_id_is_named_without_one():
    assert prefixes(route_id="R1", schedule_relationship=NUMBERS[ADDED]) == [
        "a trip with no trip_id uses schedule_relationship ADDED, which this pin deprecates"
    ]


def test_the_replacements_the_clause_recommends_are_silent():
    """The satisfying fixtures, and they are the two the sentence after the
    citation names: DUPLICATED and NEW."""
    assert prefixes(trip_id="T1", schedule_relationship=NUMBERS[DUPLICATED]) == []
    assert prefixes(trip_id="T1", schedule_relationship=NUMBERS[NEW]) == []


def test_an_undeclared_relationship_is_not_reported():
    """proto2 resolves an absent field to SCHEDULED, which no feed wrote. The
    rule reports the value a producer transmitted, so that a member deprecated
    at some later pin cannot turn every descriptor in a feed into a finding."""
    assert prefixes(trip_id="T1") == []


def test_an_explicit_scheduled_is_not_reported():
    assert prefixes(trip_id="T1", schedule_relationship=NUMBERS[SCHEDULED]) == []


def test_a_vehicle_position_and_an_alert_selector_are_reached_too():
    """E003 and E016 branch on ADDED and never object to it; the value is
    deprecated wherever a TripDescriptor rides, which is three messages."""
    feed = message(
        entity(
            "a",
            vehicle={"trip": {"trip_id": "T1", "schedule_relationship": NUMBERS[ADDED]}},
        ),
        entity(
            "b",
            alert={
                "informed_entity": [
                    {"trip": {"trip_id": "T2", "schedule_relationship": NUMBERS[ADDED]}}
                ]
            },
        ),
    )

    assert [occurrence.context[ENTITY_PATH_KEY] for occurrence in check(feed, context()) or ()] == [
        "entity[0].vehicle.trip",
        "entity[1].alert.informed_entity[0].trip",
    ]
