"""E029, against upstream's own `VehicleValidatorTest.testE029` and its ignore-shapes twin.

Every assertion marked "upstream" is transcribed from the real
`VehicleValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testE029`, lines 510-694, and `testE029IgnoreShapes`, lines 700-766), not from
a second-hand summary of it. Upstream asserts *counts* and nothing else, so
every assertion about occurrence text below is ours, read off
`VehicleValidator.java:200-232`.

Upstream drives the USF Bull Runner feed, route `A`, trip_id `2`, which is not
in this repository. `rulefixtures.minimal()` stands in with route `R1`, trip
`T1` and one four-point shape: `ON_SHAPE` is a shape vertex, standing in for its
USF Marshall Center, and `OFF_SHAPE` is a point inside the agency box and off
the shape, standing in for its University Mall. Its whole alert matrix ports
unchanged, ids substituted.

The DETOUR scan itself is tested directly in `tests/test_shared_detour_alert.py`;
what is asserted here is the six-way count matrix upstream wrote, which is how
that scan is observable from the rule.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.vehicle_bounds import DETOUR_EFFECT
from gtfs_rt_validator.rules.upstream.e029 import check
from rulefixtures import context, entity, message, minimal, occurrences, prefixes

UNKNOWN_EFFECT = V2015.enums["Alert.Effect"]["UNKNOWN_EFFECT"]

#: A vertex of `T1`'s shape, standing in for upstream's USF Marshall Center.
ON_SHAPE = (27.98, -82.42)

#: Inside the agency box and off `T1`'s shape, standing in for its University Mall.
OFF_SHAPE = (27.95, -82.35)

#: Upstream's `tripDescriptorBuilder`, with this feed's ids.
TRIP = {"trip_id": "T1", "route_id": "R1"}


def below_the_gate(tables: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    """Three shape points, which stands in for upstream's no-shapes feed.

    `GtfsMetadata.java:127` gates on `shapePoints.size() > 3`, and below the
    gate `getBufferedTripShape` answers null for every trip, which is the state
    `bullrunner-gtfs-no-shapes.zip` puts upstream in.
    """
    tables["shapes.txt"] = tables["shapes.txt"][:3]
    return tables


def vehicle(
    point: tuple[float, float] | None,
    *,
    trip: Mapping[str, object] | None = None,
    vehicle_id: str | None = "1",
) -> dict[str, object]:
    built: dict[str, object] = {}
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    if point is not None:
        built["position"] = {"latitude": point[0], "longitude": point[1]}
    if trip is not None:
        built["trip"] = dict(trip)
    return built


def alert(effect: int, **selector: object) -> dict[str, object]:
    """An Alert with one informed_entity whose `trip` carries these fields."""
    return {"effect": effect, "informed_entity": [{"trip": dict(selector)}]}


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


def with_alert(
    tmp_path: Path, built: Mapping[str, object] | None, *, ignore_shapes: bool = False
) -> Sequence[Occurrence]:
    """Upstream's shape exactly: one entity carrying the VehiclePosition *and*
    the alert, since `feedEntityBuilder.setAlert` never clears the vehicle."""
    return run(
        tmp_path,
        entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP), alert=built),
        ignore_shapes=ignore_shapes,
    )


# --- upstream's own case, stage by stage ------------------------------------


def test_nothing_fires_at_all_without_shape_data(tmp_path):
    """Upstream, testE029, stages 1 to 3: the no-shapes feed, a position on the
    campus with no trip_id, one off the trip path with no trip_id, and the same
    one with trip_id set. `expected.clear()` for all three."""
    tables = below_the_gate(minimal())

    assert run(tmp_path, entity(vehicle=vehicle(ON_SHAPE)), tables=tables) == []
    assert run(tmp_path, entity(vehicle=vehicle(OFF_SHAPE)), tables=tables) == []
    assert run(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP)), tables=tables) == []


def test_a_vehicle_with_no_position_reports_nothing(tmp_path):
    """Upstream, testE029: "No errors, if position isn't populated"."""
    assert run(tmp_path, entity(vehicle=vehicle(None))) == []


def test_a_position_on_the_trip_shape_reports_nothing_with_or_without_a_trip_id(tmp_path):
    """Upstream, testE029: the Marshall Center point, first with no trip_id and
    then with trip_id set, `expected.clear()` both times."""
    assert run(tmp_path, entity(vehicle=vehicle(ON_SHAPE))) == []
    assert run(tmp_path, entity(vehicle=vehicle(ON_SHAPE, trip=TRIP))) == []


def test_a_position_off_the_trip_shape_with_no_trip_id_reports_nothing(tmp_path):
    """Upstream, testE029: University Mall with `clearTrip()`, `expected.clear()`."""
    assert run(tmp_path, entity(vehicle=vehicle(OFF_SHAPE))) == []


def test_a_position_off_the_trip_shape_with_a_trip_id_reports_once(tmp_path):
    """Upstream, testE029: the same point with the trip_id back on,
    `expected.put(E029, 1)`. This is the only stage that fires."""
    assert len(run(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP)))) == 1


# --- upstream's alert matrix, all six variants ------------------------------


def test_a_detour_alert_for_this_trip_id_suppresses_it(tmp_path):
    """Upstream, testE029: DETOUR with the whole TripDescriptor, `expected.clear()`."""
    assert with_alert(tmp_path, alert(DETOUR_EFFECT, **TRIP)) == []


def test_a_detour_alert_for_this_route_id_suppresses_it(tmp_path):
    """Upstream, testE029: DETOUR with a TripDescriptor carrying only the
    route_id, `expected.clear()`."""
    assert with_alert(tmp_path, alert(DETOUR_EFFECT, route_id="R1")) == []


def test_a_non_detour_alert_for_this_trip_id_does_not_suppress_it(tmp_path):
    """Upstream, testE029: UNKNOWN_EFFECT with the trip_id, `expected.put(E029, 1)`."""
    assert len(with_alert(tmp_path, alert(UNKNOWN_EFFECT, **TRIP))) == 1


def test_a_non_detour_alert_for_this_route_id_does_not_suppress_it(tmp_path):
    """Upstream, testE029: UNKNOWN_EFFECT with only the route_id,
    `expected.put(E029, 1)`. Upstream's comment on this stage says "still no
    error", and its assertion says one; the assertion is what the jar does."""
    assert len(with_alert(tmp_path, alert(UNKNOWN_EFFECT, route_id="R1"))) == 1


def test_a_detour_alert_for_another_route_does_not_suppress_it(tmp_path):
    """Upstream, testE029: DETOUR with route_id `C`, `expected.put(E029, 1)`."""
    assert len(with_alert(tmp_path, alert(DETOUR_EFFECT, route_id="C"))) == 1


def test_a_detour_alert_for_another_trip_does_not_suppress_it(tmp_path):
    """Upstream, testE029: DETOUR with trip_id `10`, `expected.put(E029, 1)`."""
    assert len(with_alert(tmp_path, alert(DETOUR_EFFECT, trip_id="10"))) == 1


# --- testE029IgnoreShapes, `:700-766` ---------------------------------------


def test_ignore_shapes_silences_every_one_of_those(tmp_path):
    """Upstream, testE029IgnoreShapes: the metadata is rebuilt with
    `ignoreShapes = true` and four of the cases above are re-run, asserting
    `expected.clear()` in every one."""
    assert run(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP)), ignore_shapes=True) == []
    assert with_alert(tmp_path, alert(UNKNOWN_EFFECT, **TRIP), ignore_shapes=True) == []
    assert with_alert(tmp_path, alert(DETOUR_EFFECT, route_id="C"), ignore_shapes=True) == []
    assert with_alert(tmp_path, alert(DETOUR_EFFECT, trip_id="10"), ignore_shapes=True) == []


# --- the occurrence text, which upstream's test never looks at --------------


def test_every_occurrence_carries_this_rules_id(tmp_path):
    found = run(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP)))

    assert [occurrence.rule_id for occurrence in found] == ["E029"]


def test_the_prefix_names_the_vehicle_the_trip_the_position_and_the_buffer(tmp_path):
    """Ours, read off `:228-229`. `TRIP_BUFFER_METERS` is a `double`, so it
    renders "200.0"; `toMiles(200)` is 0.1242742 and `String.format("%.2f", ...)`
    of it is "0.12", measured on JDK 17. That `%.2f` takes no `Locale`, so its
    separator follows the JVM default."""
    expected = (
        "vehicle.id 1 trip_id T1 at (27.95,-82.35) is more than 200.0 meters "
        "(0.12 mile(s)) from the GTFS trip shape"
    )

    assert prefixes(run(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP)))) == [expected]


def test_a_vehicle_with_no_id_falls_back_to_the_entity_id(tmp_path):
    """Ours: `getVehicleId(entity, v)` at `:213`."""
    found = run(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP, vehicle_id=None)))

    assert found[0].prefix.startswith("entity ID TEST_ENTITY trip_id T1 at ")


def test_an_explicitly_empty_vehicle_id_does_not_fall_back(tmp_path):
    """Ours, measured. `getVehicleId` branches on `hasId()`
    (GtfsUtils.java:226) rather than on emptiness, so `id = ""` keeps the
    `vehicle.id ` label and the empty id sits between two spaces. The jar wrote
    this whole prefix for this position; a truthiness check would have produced
    the entity-ID fallback above and passed both of these tests."""
    found = run(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP, vehicle_id="")))

    assert found[0].prefix == (
        "vehicle.id  trip_id T1 at (27.95,-82.35) is more than 200.0 meters "
        "(0.12 mile(s)) from the GTFS trip shape"
    )


def test_the_occurrence_locates_the_vehicle_position_it_came_from(tmp_path):
    found = run(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP)))

    assert found[0].context[ENTITY_PATH_KEY] == "entity[0].vehicle"


# --- the returns that come before any geometry ------------------------------


def test_a_trip_the_static_feed_has_no_shape_for_is_not_a_finding(tmp_path):
    """Ours, `:216-219`: `getBufferedTripShape` answers null for a trip that is
    not in `trips.txt`, and the rule returns rather than reporting."""
    assert run(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip={"trip_id": "NOPE"}))) == []


def test_a_trip_descriptor_with_only_a_route_id_is_not_a_finding(tmp_path):
    """Ours, `:204-206`: the guard is `hasTripId()`, not `hasTrip()` alone."""
    assert run(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip={"route_id": "R1"}))) == []


def test_a_detour_alert_on_a_different_entity_still_suppresses_it(tmp_path):
    """Ours. `hasDetourAlert` is handed the whole entity list (`:222`), so the
    alert does not have to share an entity with the vehicle."""
    found = run(
        tmp_path,
        entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP), entity_id="one"),
        entity(alert=alert(DETOUR_EFFECT, trip_id="T1"), entity_id="two"),
    )

    assert found == []


def test_entities_are_reported_in_feed_order(tmp_path):
    found = run(
        tmp_path,
        entity(vehicle=vehicle(ON_SHAPE, trip=TRIP), entity_id="one"),
        entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP, vehicle_id="2"), entity_id="two"),
        entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP, vehicle_id="3"), entity_id="three"),
    )

    assert [occurrence.prefix.split(" trip_id ")[0] for occurrence in found] == [
        "vehicle.id 2",
        "vehicle.id 3",
    ]
