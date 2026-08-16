"""S020: a DUPLICATED VehiclePosition whose trip_id no TripUpdate created.

The pairing is across a cycle rather than within a message, because an agency
that publishes `-tu` and `-vp` separately still has to satisfy it. So this is
the second rule in the project to read `ctx.combined`, after E047 and W003, and
it obeys the same contract: the combined view reaches exactly one message per
cycle, its host, so the rule fires once per cycle rather than once per role.

Not E047, which pairs `TripDescriptor.trip_id` against
`VehicleDescriptor.id` across the two feeds. This pairs a
`TripDescriptor.trip_id` against a *different field on the other side*,
`TripUpdate.TripProperties.trip_id`, which E047 never reads.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s020 import check
from specfixtures import context, cycle_of, entity, message, prefixes

TRIP = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]
DUPLICATED = TRIP["DUPLICATED"]


def duplicating(new_trip_id: str = "T1-copy") -> dict[str, object]:
    """A TripUpdate that creates `new_trip_id` by duplicating T1."""
    return {
        "trip": {"trip_id": "T1", "schedule_relationship": DUPLICATED},
        "trip_properties": {
            "trip_id": new_trip_id,
            "start_date": "20260814",
            "start_time": "10:00:00",
        },
    }


def duplicate_vehicle(trip_id: str | None = "T1-copy", relationship: int = DUPLICATED):
    trip: dict[str, object] = {"schedule_relationship": relationship}
    if trip_id is not None:
        trip["trip_id"] = trip_id
    return {"trip": trip}


def one_role(*entities):
    """A cycle of one message, which is what a single-file run produces."""
    feed = message(*entities)
    return feed, context(cycle=cycle_of({"rt": feed}))


def run(*entities):
    feed, ctx = one_role(*entities)
    return check(feed, ctx)


def test_a_duplicate_the_cycle_created_resolves():
    found = run(entity("a", trip_update=duplicating()), entity("b", vehicle=duplicate_vehicle()))

    assert prefixes(found) == []


def test_the_trip_update_may_be_written_after_the_vehicle_position():
    """The index is built from the whole message, so entity order cannot decide
    whether a correct feed is reported."""
    found = run(entity("b", vehicle=duplicate_vehicle()), entity("a", trip_update=duplicating()))

    assert prefixes(found) == []


def test_a_duplicate_nothing_created_is_reported():
    found = run(entity("b", vehicle=duplicate_vehicle("T9-copy")))

    assert prefixes(found) == [
        "vehicle trip_id T9-copy is DUPLICATED but no TripUpdate.TripProperties.trip_id matches"
    ]


def test_the_descriptors_own_trip_id_is_not_what_it_pairs_against():
    """`:806`. The VehiclePosition's trip_id is the *new* trip, so a TripUpdate
    that duplicates T1 does not satisfy a vehicle claiming to be T1."""
    found = run(
        entity("a", trip_update=duplicating()), entity("b", vehicle=duplicate_vehicle("T1"))
    )

    assert len(found) == 1


def test_a_vehicle_that_is_not_duplicated_is_not_in_scope():
    found = run(entity("b", vehicle=duplicate_vehicle("T9", relationship=TRIP["SCHEDULED"])))

    assert prefixes(found) == []


def test_a_duplicated_vehicle_with_no_trip_id_is_reported():
    """ "must contain the value for the corresponding
    TripUpdate.TripProperties.trip_id", and it contains nothing."""
    found = run(entity("b", vehicle=duplicate_vehicle(None)))

    assert prefixes(found) == [
        "vehicle trip_id  is DUPLICATED but no TripUpdate.TripProperties.trip_id matches"
    ]


def test_a_trip_update_of_its_own_is_not_a_vehicle_position():
    assert prefixes(run(entity("a", trip_update=duplicating()))) == []


def test_the_pairing_spans_the_roles_of_one_cycle():
    """The whole reason this reads `ctx.combined`: an agency publishing `-tu`
    and `-vp` separately still has to satisfy the clause."""
    updates = message(entity("a", trip_update=duplicating()))
    positions = message(entity("b", vehicle=duplicate_vehicle()))
    cycle = cycle_of({"tu": updates, "vp": positions})

    assert prefixes(check(updates, context(cycle=cycle, role="tu", source="tu.pb"))) == []


def test_an_unresolved_duplicate_in_another_role_names_that_roles_file():
    updates = message(entity("a", trip_update=duplicating("T2-copy")))
    positions = message(entity("b", vehicle=duplicate_vehicle()))
    cycle = cycle_of({"tu": updates, "vp": positions})

    found = check(updates, context(cycle=cycle, role="tu", source="tu.pb"))

    assert [occurrence.context["sourceFile"] for occurrence in found] == ["vp.pb"]
    assert [occurrence.context["entityPath"] for occurrence in found] == ["entity[0].vehicle"]
    assert [occurrence.rule_id for occurrence in found] == ["S020"]


def test_a_message_that_is_not_its_cycles_host_says_nothing():
    """`ctx.combined` is `None` on every message but the host, and the host has
    already reported the whole cycle."""
    feed = message(entity("b", vehicle=duplicate_vehicle("T9-copy")))

    assert check(feed, context()) is None
