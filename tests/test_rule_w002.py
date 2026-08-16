"""W002, against upstream's own `VehicleValidatorTest.testW002`.

Every assertion marked "upstream" is transcribed from the real
`VehicleValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testW002`, lines 54-94), not from a second-hand summary of it. Upstream
asserts *counts* and nothing else, so every assertion about occurrence text
below is ours, read off `VehicleValidator.java:73-86`.

Upstream builds one FeedEntity carrying both a TripUpdate and a VehiclePosition,
which is what makes the two sites countable in one call, and this ports that
shape. Its two halves do **not** share a helper: the TripUpdate half calls
`getTripId(entity, tripUpdate)` and the VehiclePosition half writes
`"entity ID " + entity.getId()` inline, so a vehicle with a trip_id and no
vehicle_id gets two differently shaped prefixes out of one entity.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules.upstream.w002 import check
from rulefixtures import context, entity, message, minimal, occurrences, prefixes


def descriptor(vehicle_id: str | None) -> dict[str, object]:
    """A VehicleDescriptor, or nothing at all when `vehicle_id` is `None`."""
    return {} if vehicle_id is None else {"vehicle": {"id": vehicle_id}}


def trip_update(vehicle_id: str | None, trip_id: str | None = None) -> dict[str, object]:
    trip: dict[str, object] = {} if trip_id is None else {"trip_id": trip_id}
    return {"trip": trip, **descriptor(vehicle_id)}


def vehicle(vehicle_id: str | None) -> dict[str, object]:
    return descriptor(vehicle_id)


def run(tmp_path: Path, *entities: Mapping[str, object]) -> Sequence[Occurrence]:
    return occurrences(check(message(*entities), context(tmp_path, minimal())))


# --- upstream's own case, stage by stage ------------------------------------


def test_a_vehicle_id_on_both_halves_reports_nothing(tmp_path):
    """Upstream, testW002: vehicle.id `1` on the TripUpdate and the
    VehiclePosition of one entity, `expected.clear()`."""
    found = run(tmp_path, entity(trip_update=trip_update("1"), vehicle=vehicle("1")))

    assert found == []


def test_an_empty_vehicle_id_on_both_halves_reports_twice(tmp_path):
    """Upstream, testW002: `expected.put(W002, 2)`, "one for TripUpdates and
    one for VehiclePositions"."""
    found = run(tmp_path, entity(trip_update=trip_update(""), vehicle=vehicle("")))

    assert len(found) == 2


# --- the occurrence text, which upstream's test never looks at --------------


def test_every_occurrence_carries_this_rules_id(tmp_path):
    found = run(tmp_path, entity(vehicle=vehicle("")))

    assert [occurrence.rule_id for occurrence in found] == ["W002"]


def test_the_trip_update_half_names_the_trip(tmp_path):
    """Ours, read off `:78`: `getTripId(entity, tripUpdate)`."""
    found = run(tmp_path, entity(trip_update=trip_update("", trip_id="T1")))

    assert prefixes(found) == ["trip_id T1"]


def test_a_trip_update_with_no_trip_id_falls_back_to_the_entity_id(tmp_path):
    """Ours. Upstream's own testW002 builds exactly this descriptor, an empty
    one, so this is the text the jar emits for its own feed."""
    found = run(tmp_path, entity(trip_update=trip_update("")))

    assert prefixes(found) == ["entity ID TEST_ENTITY"]


def test_the_vehicle_position_half_always_names_the_entity(tmp_path):
    """Ours, and the asymmetry worth knowing: `:86` writes
    `"entity ID " + entity.getId()` inline rather than calling
    `getVehicleId`, so there is no trip_id or vehicle.id form of this half."""
    found = run(tmp_path, entity(vehicle=vehicle(""), entity_id="V1"))

    assert prefixes(found) == ["entity ID V1"]


def test_one_entity_reports_the_trip_update_before_the_vehicle_position(tmp_path):
    """Ours: `:73` runs before `:81`, and the two prefixes differ in shape."""
    found = run(
        tmp_path,
        entity(trip_update=trip_update("", trip_id="T1"), vehicle=vehicle(""), entity_id="E1"),
    )

    assert prefixes(found) == ["trip_id T1", "entity ID E1"]


def test_each_occurrence_locates_the_half_it_came_from(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update(""), vehicle=vehicle("")))

    assert [occurrence.context[ENTITY_PATH_KEY] for occurrence in found] == [
        "entity[0].trip_update",
        "entity[0].vehicle",
    ]


# --- the missing guard, which is the rule ----------------------------------


def test_a_trip_update_with_no_vehicle_descriptor_at_all_reports(tmp_path):
    """Ours. `:76` has no `hasVehicle()` guard, so `getVehicle()` answers the
    default instance and `getId()` answers `""`, which is what fires."""
    found = run(tmp_path, entity(trip_update=trip_update(None)))

    assert prefixes(found) == ["entity ID TEST_ENTITY"]


def test_a_vehicle_position_with_no_vehicle_descriptor_at_all_reports(tmp_path):
    """Ours, `:84`, for the same reason."""
    found = run(tmp_path, entity(vehicle=vehicle(None)))

    assert prefixes(found) == ["entity ID TEST_ENTITY"]


def test_an_entity_carrying_neither_half_reports_nothing(tmp_path):
    assert run(tmp_path, entity()) == []


def test_entities_are_reported_in_feed_order(tmp_path):
    found = run(
        tmp_path,
        entity(vehicle=vehicle(""), entity_id="one"),
        entity(vehicle=vehicle("2"), entity_id="two"),
        entity(vehicle=vehicle(""), entity_id="three"),
    )

    assert prefixes(found) == ["entity ID one", "entity ID three"]
