"""E028, against upstream's own `VehicleValidatorTest.testE028` and the shapes gate.

Every assertion marked "upstream" is transcribed from the real
`VehicleValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testE028`, lines 422-504), not from a second-hand summary of it. Upstream
asserts *counts* and nothing else, so every assertion about occurrence text
below is ours, read off `VehicleValidator.java:164-190`.

Upstream's four stages run against `bullrunner-gtfs.zip` and
`bullrunner-gtfs-no-shapes.zip`, neither of which is in this repository, so the
*shape* of its case is ported and its coordinates are not. `rulefixtures.minimal()`
gives one agency around Tampa with four shape points, exactly one more than the
gate needs; a position inside it stands in for upstream's USF campus, and New
York stands in for its downtown Tampa. The geometry those verdicts rest on is
already pinned to spatial4j 0.6 by `tests/test_bbox.py`.

Upstream's own no-shapes stage asserts the same two verdicts as its with-shapes
stage and never looks at the text, which is exactly what it cannot see: the box
and the word in the message both change. Both are tested here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules.upstream.e028 import check
from rulefixtures import context, entity, message, minimal, occurrences, prefixes

#: Inside the agency box of `minimal()`, standing in for upstream's USF campus.
INSIDE = (27.98, -82.42)

#: New York City, standing in for upstream's downtown Tampa: valid WGS84, so it
#: reaches E028, and well outside a one-mile buffer around Tampa.
OUTSIDE = (40.7128, -74.0059)

NEW_YORK_STOP = {
    "stop_id": "NYC",
    "stop_name": "Far",
    "stop_lat": "40.7128",
    "stop_lon": "-74.0059",
    "location_type": "0",
}


def below_the_gate(tables: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    """The same feed with three shape points, which is one too few.

    `GtfsMetadata.java:127` gates on `shapePoints.size() > 3`, so four points
    open it and three shut it. Below the gate there is no shapes box at all.
    """
    tables["shapes.txt"] = tables["shapes.txt"][:3]
    return tables


def reaching_new_york(tables: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    """The same feed with one stop in New York and its shape still in Tampa.

    Which is what makes the gate observable in the verdict rather than only in
    the text: the stops box now contains a point the shapes box does not.
    """
    tables["stops.txt"].append(dict(NEW_YORK_STOP))
    return tables


def vehicle(
    point: tuple[float, float] | None, *, vehicle_id: str | None = "1"
) -> dict[str, object]:
    built: dict[str, object] = {}
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    if point is not None:
        built["position"] = {"latitude": point[0], "longitude": point[1]}
    return built


def run(
    tmp_path: Path,
    *entities: Mapping[str, object],
    tables: dict[str, list[dict[str, str]]] | None = None,
    ignore_shapes: bool = False,
) -> Sequence[Occurrence]:
    ctx = context(
        tmp_path, tables if tables is not None else minimal(), ignore_shapes=ignore_shapes
    )
    return occurrences(check(message(*entities), ctx))


def at(tmp_path: Path, point: tuple[float, float] | None, **kwargs: object) -> Sequence[Occurrence]:
    return run(tmp_path, entity(vehicle=vehicle(point)), **kwargs)  # type: ignore[arg-type]


# --- upstream's own case, stage by stage ------------------------------------


def test_a_vehicle_with_no_position_reports_nothing(tmp_path):
    """Upstream, testE028: "No errors, if position isn't populated"."""
    assert at(tmp_path, None) == []


def test_a_position_inside_the_agency_area_reports_nothing(tmp_path):
    """Upstream, testE028, stage 2: its USF campus point, `expected.clear()`.
    Ours is a point inside `minimal()`'s box, since the bull runner feed is not
    in this repository."""
    assert at(tmp_path, INSIDE) == []


def test_a_position_outside_the_agency_area_reports_once(tmp_path):
    """Upstream, testE028, stage 3: its downtown Tampa point,
    `expected.put(E028, 1)`. Ours is New York."""
    assert len(at(tmp_path, OUTSIDE)) == 1


def test_the_same_two_verdicts_hold_with_no_shapes_box(tmp_path):
    """Upstream, testE028, stages 4 and 5, which re-run both positions against
    `bullrunner-gtfs-no-shapes.zip` and assert the same counts. Here the shapes
    box is removed by shutting the gate rather than by deleting the file."""
    assert at(tmp_path, INSIDE, tables=below_the_gate(minimal())) == []
    assert len(at(tmp_path, OUTSIDE, tables=below_the_gate(minimal()))) == 1


# --- the occurrence text, which upstream's test never looks at --------------


def test_every_occurrence_carries_this_rules_id(tmp_path):
    assert [found.rule_id for found in at(tmp_path, OUTSIDE)] == ["E028"]


def test_the_prefix_names_the_vehicle_the_position_and_the_buffer(tmp_path):
    """Ours, read off `:184-186`. `REGION_BUFFER_METERS` is a `double`, so it
    renders "1609.0" and never "1609"; `toMiles(1609)` is 0.999785... and
    `String.format("%.2f", ...)` of it is "1.00", measured on JDK 17. That
    `%.2f` takes no `Locale`, so its separator follows the JVM default."""
    expected = (
        "vehicle.id 1 at (40.7128,-74.0059) is more than 1609.0 meters "
        "(1.00 mile(s)) outside entire GTFS shapes.txt coverage area"
    )

    assert prefixes(at(tmp_path, OUTSIDE)) == [expected]


def test_the_text_says_stops_txt_below_the_shapes_gate(tmp_path):
    """Ours, and an output-byte difference upstream's own test cannot see:
    `boundingDescription` is `"shapes.txt"` only while
    `getShapeBoundingBoxWithBuffer()` is non-null."""
    found = at(tmp_path, OUTSIDE, tables=below_the_gate(minimal()))

    assert found[0].prefix.endswith("outside entire GTFS stops.txt coverage area")


def test_the_text_says_stops_txt_under_ignore_shapes(tmp_path):
    """Ours: the flag leaves the same field null, by the same `:127` condition."""
    found = at(tmp_path, OUTSIDE, ignore_shapes=True)

    assert found[0].prefix.endswith("outside entire GTFS stops.txt coverage area")


def test_a_vehicle_with_no_id_falls_back_to_the_entity_id(tmp_path):
    """Ours: `getVehicleId(entity, v)` at `:167`."""
    found = run(tmp_path, entity(vehicle=vehicle(OUTSIDE, vehicle_id=None)))

    assert found[0].prefix.startswith("entity ID TEST_ENTITY at (40.7128,-74.0059)")


def test_an_explicitly_empty_vehicle_id_does_not_fall_back(tmp_path):
    """Ours, measured. `getVehicleId` branches on `hasId()`
    (GtfsUtils.java:226) rather than on emptiness, so `id = ""` keeps the
    `vehicle.id ` label. The jar wrote this whole prefix for this position; a
    truthiness check would have produced the entity-ID fallback above and passed
    both of these tests."""
    found = run(tmp_path, entity(vehicle=vehicle(OUTSIDE, vehicle_id="")))

    assert found[0].prefix == (
        "vehicle.id  at (40.7128,-74.0059) is more than 1609.0 meters "
        "(1.00 mile(s)) outside entire GTFS shapes.txt coverage area"
    )


def test_the_occurrence_locates_the_vehicle_position_it_came_from(tmp_path):
    found = at(tmp_path, OUTSIDE)

    assert found[0].context[ENTITY_PATH_KEY] == "entity[0].vehicle"


# --- the gate decides which box is asked, not only which word is written ----


def test_four_shape_points_measure_against_the_shapes_box(tmp_path):
    """Ours. The feed's stops now reach New York and its shape does not, so a
    vehicle in New York is outside the shapes box and inside the stops box."""
    tables = reaching_new_york(minimal())

    assert len(at(tmp_path, OUTSIDE, tables=tables)) == 1


def test_three_shape_points_measure_against_the_stops_box(tmp_path):
    """Ours, the same feed one shape point shorter. The verdict flips, which is
    what makes the miscount worth guarding: four points open the gate."""
    tables = below_the_gate(reaching_new_york(minimal()))

    assert at(tmp_path, OUTSIDE, tables=tables) == []


def test_entities_are_reported_in_feed_order(tmp_path):
    found = run(
        tmp_path,
        entity(vehicle=vehicle(INSIDE), entity_id="one"),
        entity(vehicle=vehicle(OUTSIDE, vehicle_id="2"), entity_id="two"),
        entity(vehicle=vehicle(OUTSIDE, vehicle_id="3"), entity_id="three"),
    )

    assert [occurrence.prefix.split(" at ")[0] for occurrence in found] == [
        "vehicle.id 2",
        "vehicle.id 3",
    ]
