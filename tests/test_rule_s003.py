"""S003: two TripUpdate entities describing one trip instance.

The instance is `(trip_id, start_date, start_time)`, which is the key the
`TripDescriptor` comment itself gives at `:803-806`: "For non frequency-based
trips, this field is enough to uniquely identify the trip. For frequency-based
trip, start_time and start_date might also be necessary." So two descriptors
that differ in `start_date` are two instances, and two that agree on all three
are one.

A descriptor with no `trip_id` names no instance at all: it is the route-scoped
form, which `:797` describes and which S018 and S019 are about. It is skipped
here rather than keyed under the empty string, which would collapse every
route-scoped TripUpdate in a feed into one imaginary trip.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.spec.s003 import check
from rulefixtures import trip_rows
from specfixtures import context, entity, feed_context, message, minimal, prefixes


def trip_update(**descriptor: object) -> dict[str, object]:
    return {"trip": dict(descriptor)}


def run(*entities):
    return check(message(*entities), context())


def test_two_trip_updates_for_different_trips_are_not_a_finding():
    found = run(
        entity("a", trip_update=trip_update(trip_id="T1")),
        entity("b", trip_update=trip_update(trip_id="T2")),
    )

    assert prefixes(found) == []


def test_two_trip_updates_for_one_trip_id_are_reported():
    found = run(
        entity("a", trip_update=trip_update(trip_id="T1")),
        entity("b", trip_update=trip_update(trip_id="T1")),
    )

    assert prefixes(found) == ["trip_id T1 has 2 TripUpdate entities"]


def test_a_different_start_date_makes_it_a_different_instance():
    found = run(
        entity("a", trip_update=trip_update(trip_id="T1", start_date="20260814")),
        entity("b", trip_update=trip_update(trip_id="T1", start_date="20260815")),
    )

    assert prefixes(found) == []


def test_the_same_start_date_and_start_time_make_it_the_same_instance():
    found = run(
        entity(
            "a", trip_update=trip_update(trip_id="T1", start_date="20260814", start_time="10:00:00")
        ),
        entity(
            "b", trip_update=trip_update(trip_id="T1", start_date="20260814", start_time="10:00:00")
        ),
    )

    assert prefixes(found) == [
        "trip_id T1 start_date 20260814 start_time 10:00:00 has 2 TripUpdate entities"
    ]


def test_one_descriptor_naming_a_start_date_and_one_omitting_it_are_two_instances():
    """Absent is not the same key as present-and-equal here, because the clause
    is about the instance a descriptor names and an omitted `start_date` names
    every service date at once."""
    found = run(
        entity("a", trip_update=trip_update(trip_id="T1")),
        entity("b", trip_update=trip_update(trip_id="T1", start_date="20260814")),
    )

    assert prefixes(found) == []


def test_a_stated_start_time_does_not_split_a_non_frequency_instance(tmp_path: Path):
    """`:817`: on a non-frequency trip the field "should either be omitted or be
    equal to the value in the GTFS feed", so it distinguishes nothing and both
    descriptors name the instance `:803` says `trip_id` alone identifies."""
    ctx = feed_context(tmp_path, minimal(trips=trip_rows({"T2": "R1"})))
    found = check(
        message(
            entity("a", trip_update=trip_update(trip_id="T2", start_date="20260815")),
            entity(
                "b",
                trip_update=trip_update(trip_id="T2", start_date="20260815", start_time="08:00:00"),
            ),
        ),
        ctx,
    )

    assert prefixes(found) == ["trip_id T2 start_date 20260815 has 2 TripUpdate entities"]


def test_a_stated_start_time_still_splits_a_frequency_based_instance(tmp_path: Path):
    """`T1` is `minimal_tables()`'s own `frequencies.txt` trip. There `:817`
    requires the field, so a descriptor that omits it names something else."""
    ctx = feed_context(tmp_path)
    found = check(
        message(
            entity("a", trip_update=trip_update(trip_id="T1", start_date="20260815")),
            entity(
                "b",
                trip_update=trip_update(trip_id="T1", start_date="20260815", start_time="08:00:00"),
            ),
        ),
        ctx,
    )

    assert prefixes(found) == []


def test_a_trip_the_static_feed_does_not_have_keeps_its_start_time(tmp_path: Path):
    """An ADDED trip has no scheduled start time to be redundant with, so the
    two halves of the key stay as the descriptors state them."""
    ctx = feed_context(tmp_path)
    found = check(
        message(
            entity("a", trip_update=trip_update(trip_id="NOPE", start_date="20260815")),
            entity(
                "b",
                trip_update=trip_update(
                    trip_id="NOPE", start_date="20260815", start_time="08:00:00"
                ),
            ),
        ),
        ctx,
    )

    assert prefixes(found) == []


def test_a_trip_update_with_no_trip_id_names_no_instance():
    """The route-scoped form. Two of them are not two of anything."""
    found = run(
        entity("a", trip_update=trip_update(route_id="R1")),
        entity("b", trip_update=trip_update(route_id="R1")),
    )

    assert prefixes(found) == []


def test_a_vehicle_position_sharing_the_trip_is_not_a_trip_update():
    """ "at most one TripUpdate entity", and a VehiclePosition for the same trip
    is the pairing E047 and W003 are about."""
    found = run(
        entity("a", trip_update=trip_update(trip_id="T1")),
        entity("b", vehicle={"trip": {"trip_id": "T1"}}),
    )

    assert prefixes(found) == []


def test_the_occurrence_names_every_entity_index_that_claimed_the_instance():
    found = run(
        entity("a", trip_update=trip_update(trip_id="T1")),
        entity("b", trip_update=trip_update(trip_id="T2")),
        entity("c", trip_update=trip_update(trip_id="T1")),
    )

    assert [occurrence.context["entityIndexes"] for occurrence in found] == [[0, 2]]
    assert [occurrence.rule_id for occurrence in found] == ["S003"]
