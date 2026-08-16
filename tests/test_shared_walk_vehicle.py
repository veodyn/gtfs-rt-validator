"""`VehicleValidator`'s single pass, and the nesting four of its rules share.

What is asserted here is control flow, not occurrence text: which rules a given
VehiclePosition can reach, and in which order the one loop emits them. The text
each rule builds out of these events is pinned in the seven `test_rule_*` files,
and the alert scan E029 uses is in `test_shared_detour_alert.py`.

Upstream's own `VehicleValidatorTest` asserts counts per rule and never looks at
the loop, so nothing in this file is a transcription of it; every assertion here
is ours, read off `VehicleValidator.java:72-129`. The one that matters most is
`test_a_position_outside_the_agency_box_never_reaches_e029`: E029 is inside
`if (insideBounds)`, so a rule evaluating its own condition would report a
vehicle in New York against a Tampa trip shape, which the jar never does.

The feed is `rulefixtures.minimal()`: one trip `T1` over four shape points
running south-west to north-east across Tampa, which is exactly one more point
than the shapes gate needs. The bull runner feeds upstream's own test uses are
not in this repository, so the three points below were measured against this
project's own `geometry/`, already pinned to spatial4j 0.6 and JTS 1.13 by
`tests/test_bbox.py` and `tests/test_buffer.py`, rather than ported.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.vehicle_bounds import DETOUR_EFFECT, TRIP_BUFFER_METERS
from gtfs_rt_validator.rules._shared.walk_vehicle import (
    MAX_REALISTIC_SPEED_METERS_PER_SECOND,
    vehicles,
)
from gtfs_rt_validator.rules._shared.walks import Event, walk_events
from gtfs_rt_validator.static.context import TRIP_BUFFER_METERS as STATIC_TRIP_BUFFER_METERS
from rulefixtures import context, entity, message, minimal, static_context

#: On `T1`'s shape and inside the agency box: nothing fires.
ON_SHAPE = (27.98, -82.42)

#: Inside the agency box, off `T1`'s shape: E028 passes, E029 fires.
OFF_SHAPE = (27.95, -82.35)

#: New York City. Outside the agency box *and* outside the trip shape, which is
#: what makes the nesting observable at all.
FAR_AWAY = (40.7128, -74.0059)

#: `trips.txt`'s only trip in `minimal()`, and the one with a shape.
TRIP = {"trip_id": "T1", "route_id": "R1"}


def vehicle(
    point: tuple[float, float] | None = None,
    *,
    vehicle_id: str | None = "1",
    trip: Mapping[str, object] | None = None,
    **extra: float,
) -> dict[str, object]:
    """One VehiclePosition. `vehicle_id=None` leaves the descriptor off entirely."""
    built: dict[str, object] = {}
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    if point is not None:
        built["position"] = {"latitude": point[0], "longitude": point[1], **extra}
    if trip is not None:
        built["trip"] = dict(trip)
    return built


def walk(
    tmp_path: Path, *entities: Mapping[str, object], ignore_shapes: bool = False
) -> list[Event]:
    ctx = context(tmp_path, minimal(), ignore_shapes=ignore_shapes)
    return list(vehicles(message(*entities), ctx))


def ids(events: Sequence[Event]) -> list[str]:
    return [event.rule_id for event in events]


# --- the nesting, which is the reason this walk exists -----------------------


def test_a_position_outside_the_agency_box_never_reaches_e029(tmp_path):
    """E029 sits inside `if (insideBounds)` (`:118-121`), so a position that
    failed E028 is never measured against the trip shape."""
    found = walk(tmp_path, entity(vehicle=vehicle(FAR_AWAY, trip=TRIP)))

    assert ids(found) == ["E028"]


def test_that_far_away_position_really_is_outside_the_trip_shape_too(tmp_path):
    """The other half of the test above: without the nesting, E029's own
    condition holds here, so a rule that evaluated it independently would
    report New York against a Tampa trip shape."""
    shape = static_context(tmp_path, minimal()).buffered_trip_shape("T1")
    latitude, longitude = FAR_AWAY

    assert shape is not None
    assert not shape.contains(longitude, latitude)


def test_a_position_inside_the_box_but_off_the_trip_shape_reports_e029(tmp_path):
    found = walk(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP)))

    assert ids(found) == ["E029"]


def test_a_position_on_the_trip_shape_reports_nothing(tmp_path):
    found = walk(tmp_path, entity(vehicle=vehicle(ON_SHAPE, trip=TRIP)))

    assert found == []


def test_an_invalid_position_reports_e026_and_neither_geometry_rule(tmp_path):
    """`:112-115`: the geometry branch is the `else` of the E026 chain."""
    found = walk(tmp_path, entity(vehicle=vehicle((1000.0, -82.42), trip=TRIP)))

    assert ids(found) == ["E026"]


def test_e027_is_outside_the_e026_chain_but_inside_has_position(tmp_path):
    """`:123-126` is a sibling of the if/else, not a branch of it, so an invalid
    position and an invalid bearing are reported together."""
    found = walk(tmp_path, entity(vehicle=vehicle((1000.0, -82.42), bearing=361.0)))

    assert ids(found) == ["E026", "E027"]


def test_a_vehicle_with_no_position_reaches_none_of_the_four(tmp_path):
    found = walk(tmp_path, entity(vehicle=vehicle(None)))

    assert found == []


def test_e029_needs_a_trip_id_on_the_vehicle(tmp_path):
    """`:204-206`. The same point that reports E029 above reports nothing with
    no TripDescriptor, and nothing with one that carries only a route_id."""
    assert ids(walk(tmp_path, entity(vehicle=vehicle(OFF_SHAPE)))) == []
    assert ids(walk(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip={"route_id": "R1"})))) == []


def test_e029_needs_a_trip_the_static_feed_has_a_shape_for(tmp_path):
    """`getBufferedTripShape` returns null for a trip that is not in
    `trips.txt`, and `:216-219` returns rather than reporting."""
    found = walk(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip={"trip_id": "NOPE"})))

    assert found == []


def test_ignore_shapes_disables_e029_silently(tmp_path):
    """Every trip shape is null under the flag, so the position that fires E029
    above fires nothing at all. E028 still runs, against the stops box."""
    found = walk(tmp_path, entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP)), ignore_shapes=True)

    assert found == []


def test_a_detour_alert_anywhere_in_the_feed_suppresses_e029(tmp_path):
    """`:222-225`, wired up. The scan itself is `test_shared_detour_alert.py`."""
    detour = {"effect": DETOUR_EFFECT, "informed_entity": [{"trip": {"trip_id": "T1"}}]}
    found = walk(
        tmp_path,
        entity(vehicle=vehicle(OFF_SHAPE, trip=TRIP), entity_id="one"),
        entity(alert=detour, entity_id="two"),
    )

    assert found == []


# --- emission order inside one entity ----------------------------------------


def test_the_within_entity_order_is_the_java_order(tmp_path):
    """`:73-127`: the TripUpdate half first, then W002 or E052, then W004, then
    the E026 chain, then E027. Only the per-rule order reaches output bytes, but
    this is the order the loop yields in and every rule reads it in."""
    found = walk(
        tmp_path,
        entity(
            trip_update={"trip": {"trip_id": "T1"}},
            vehicle=vehicle(FAR_AWAY, vehicle_id=None, bearing=361.0, speed=31.0),
        ),
    )

    assert ids(found) == ["W002", "W002", "W004", "E028", "E027"]


def test_entities_are_walked_in_feed_order(tmp_path):
    found = walk(
        tmp_path,
        entity(vehicle=vehicle(FAR_AWAY), entity_id="one"),
        entity(vehicle=vehicle((1000.0, 0.0), vehicle_id="2"), entity_id="two"),
    )

    assert ids(found) == ["E028", "E026"]


def test_every_event_carries_the_entity_path_it_was_found_at(tmp_path):
    found = walk(
        tmp_path,
        entity(trip_update={"trip": {}}),
        entity(vehicle=vehicle(FAR_AWAY, vehicle_id="")),
    )

    assert [event.context[ENTITY_PATH_KEY] for event in found] == [
        "entity[0].trip_update",
        "entity[1].vehicle",
        "entity[1].vehicle",
    ]


# --- the per-message state E052 needs ----------------------------------------


def test_the_vehicle_id_set_spans_the_whole_message(tmp_path):
    """`vehicleIds` is built once per `validate` call (`:70`), so the duplicate
    is found across entities and only the second copy is reported."""
    found = walk(
        tmp_path,
        entity(vehicle=vehicle(ON_SHAPE), entity_id="one"),
        entity(vehicle=vehicle(ON_SHAPE), entity_id="two"),
    )

    assert ids(found) == ["E052"]


def test_an_empty_vehicle_id_is_w002_and_is_never_considered_for_e052(tmp_path):
    """E052 lives in the `else` of the W002 test (`:84-94`), so two blank ids
    are two warnings and no error."""
    found = walk(
        tmp_path,
        entity(vehicle=vehicle(ON_SHAPE, vehicle_id=""), entity_id="one"),
        entity(vehicle=vehicle(ON_SHAPE, vehicle_id=""), entity_id="two"),
    )

    assert ids(found) == ["W002", "W002"]


# --- the memo, and the constants that reach output bytes ---------------------


def test_the_walk_body_runs_once_however_many_rules_read_it(tmp_path):
    """`walk_events` caches on `ctx.memo`, so seven rules walk one feed once."""
    ctx = context(tmp_path, minimal())
    built = message(entity(vehicle=vehicle(FAR_AWAY)))

    first = walk_events(vehicles, built, ctx)
    second = walk_events(vehicles, built, ctx)

    assert first is second
    assert ids(first) == ["E028"]


def test_the_max_realistic_speed_is_the_float_the_java_declares():
    """`:57` declares `26.0f`, which is exactly representable, so the narrowing
    is a no-op and the comparison is the same in either width. Pinned because
    the constant is the whole of what W004 compares against."""
    assert MAX_REALISTIC_SPEED_METERS_PER_SECOND == 26.0


def test_the_trip_buffer_constant_matches_the_static_layers_copy():
    """`GtfsMetadata.java:44`, declared twice in this project because the rules
    layer may not import `static/`; see
    `tests/test_only_adapter_touches_the_sibling.py`. This is what stops the
    two drifting."""
    assert TRIP_BUFFER_METERS == STATIC_TRIP_BUFFER_METERS
