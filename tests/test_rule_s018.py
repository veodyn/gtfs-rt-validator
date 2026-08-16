"""S018, and the band it occupies that E040 leaves open.

There is no oracle for an S rule: the jar implements none of them. What the jar
*can* do is refute a declared overlap. S018 declares two, E040 and W006 in
`OVERLAP` in `tests/test_tier_overlap.py`, and the one this module is about is
E040. The disjointness claim is that E040 accepts a stop_time_update carrying
only a `stop_sequence`, and that the proto does not accept it when the trip is
named by route alone. `tests/test_spec_tier_does_not_shadow_the_jar.py` is where the jar
is actually asked; what is asserted here is the predicate.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s018 import check
from specfixtures import context, entity, message


def found(*updates, **trip):
    """S018 over one TripUpdate whose descriptor is `trip`."""
    feed = message(entity(trip_update={"trip": dict(trip), "stop_time_update": list(updates)}))
    return list(check(feed, context()) or ())


def prefixes(*updates, **trip):
    return [occurrence.prefix for occurrence in found(*updates, **trip)]


def test_a_route_scoped_update_with_only_a_stop_sequence_reports():
    """The band E040 accepts and the proto does not: no trip_id to resolve the
    sequence against, so no consumer can say which stop this is about."""
    assert prefixes({"stop_sequence": 3}, route_id="R1") == [
        "route_id R1 stop_time_update[0] has no stop_id"
    ]


def test_the_occurrence_locates_the_update_that_is_missing_the_stop_id():
    (occurrence,) = found({"stop_id": "S1"}, {"stop_sequence": 3}, route_id="R1")

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].trip_update.stop_time_update[1]"


def test_every_update_missing_a_stop_id_reports_once():
    assert len(prefixes({"stop_sequence": 1}, {"stop_sequence": 2}, route_id="R1")) == 2


def test_a_route_scoped_update_carrying_stop_ids_is_silent():
    """The satisfying fixture. With no oracle, over-firing is the failure that
    ships, so this is not optional."""
    assert prefixes({"stop_id": "S1", "stop_sequence": 1}, route_id="R1") == []


def test_a_trip_scoped_descriptor_is_out_of_scope_however_bare_its_updates():
    """The clause's antecedent is "if the trip_id is not known". A trip_id makes
    a stop_sequence resolvable against stop_times.txt, which is E045's and
    E051's ground, not this rule's."""
    assert prefixes({"stop_sequence": 3}, trip_id="T1", route_id="R1") == []


def test_a_descriptor_naming_neither_is_out_of_scope():
    """W006 reports the missing trip_id. This clause is about the route-scoped
    form specifically, which is the one the proto blesses."""
    assert prefixes({"stop_sequence": 3}) == []


def test_a_trip_update_with_no_stop_time_updates_is_silent():
    assert prefixes(route_id="R1") == []


def test_a_vehicle_position_carries_no_stop_time_updates_and_so_no_finding():
    """The clause names TripUpdate, and `stop_time_update` exists nowhere else."""
    feed = message(entity(vehicle={"trip": {"route_id": "R1"}}))

    assert list(check(feed, context()) or ()) == []
