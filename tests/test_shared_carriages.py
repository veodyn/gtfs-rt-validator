"""The per-vehicle carriage walk, read by S051 and S052.

Two claims. The carriages stay grouped by the VehiclePosition that declares
them, which is what "unique per vehicle" and "the first carriage in the
direction of travel" both need and what a flat stream would lose. And two rules
reading it in one context walk the entities once.
"""

from __future__ import annotations

from gtfs_rt_validator.rules._shared import carriages
from gtfs_rt_validator.rules._shared.carriages import vehicle_carriages
from specfixtures import context, entity, message, sharing


def vehicle(*ids: str) -> dict[str, object]:
    return {
        "trip": {"trip_id": "T1"},
        "multi_carriage_details": [{"id": name} for name in ids],
    }


def test_each_vehicle_keeps_its_own_carriages():
    walked = vehicle_carriages(
        message(
            entity("one", vehicle=vehicle("A", "B")),
            entity("two", vehicle=vehicle("A")),
        ),
        context(),
    )

    assert [(record.entity_id, len(record.carriages)) for record in walked] == [
        ("one", 2),
        ("two", 1),
    ]


def test_a_vehicle_with_no_carriages_is_still_yielded():
    """A rule that wants only the populated ones filters. A walk that dropped
    them would make "this vehicle declares none" unsayable."""
    walked = vehicle_carriages(
        message(entity("one", vehicle={"trip": {"trip_id": "T1"}})), context()
    )

    assert [(record.entity_id, record.carriages) for record in walked] == [("one", ())]


def test_an_entity_carrying_no_vehicle_is_not_walked():
    walked = vehicle_carriages(
        message(entity("one", trip_update={"trip": {"trip_id": "T1"}})), context()
    )

    assert walked == ()


def test_the_paths_locate_the_vehicle_and_each_carriage():
    walked = vehicle_carriages(message(entity("a"), entity("b", vehicle=vehicle("A"))), context())

    assert [record.path for record in walked] == ["entity[1].vehicle"]
    assert walked[0].carriage_path(0) == "entity[1].vehicle.multi_carriage_details[0]"


def test_two_rules_sharing_one_context_walk_the_entities_once(monkeypatch):
    """S051 and S052 read one message; a walk that reran per rule would cost a
    second pass that no assertion about output could notice."""
    runs = sharing(monkeypatch, carriages, "_build")
    feed = message(entity("one", vehicle=vehicle("A", "B")))
    ctx = context()

    assert len(vehicle_carriages(feed, ctx)) == 1
    assert len(vehicle_carriages(feed, ctx)[0].carriages) == 2

    assert runs == [feed]
