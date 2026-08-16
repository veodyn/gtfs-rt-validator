"""`_shared/realtime_shapes`: the join from a trip_id to a published `Shape`.

Two things are worth a test rather than a sentence. The **order** of the entities
must not matter, because a feed may publish a `Shape` before or after the
TripUpdate that names it and nothing obliges it to choose. And the points must
come out `(lon, lat)`, because `_shared/polyline` answers the encoding's own
`(latitude, longitude)` and every geometric thing in this project is the other
way round; a swap that was forgotten would measure a distance across the world
and still return a number.
"""

from __future__ import annotations

from gtfs_rt_validator.rules._shared import realtime_shapes
from gtfs_rt_validator.rules._shared.realtime_shapes import Points, shapes_by_trip
from p015fixtures import encode_polyline
from specfixtures import context, cycle_of, entity, message, sharing

POINTS = [(60.0, 10.0), (60.1, 10.2)]

#: The same points as the module answers them: `(lon, lat)`, not the encoding's
#: `(lat, lon)`.
SWAPPED = ((10.0, 60.0), (10.2, 60.1))

SHAPE = {"shape_id": "RT1", "encoded_polyline": encode_polyline(POINTS)}


def properties(trip_id: str = "T1", **rest: object) -> dict[str, object]:
    return {"trip": {"trip_id": trip_id}, "trip_properties": {"shape_id": "RT1", **rest}}


def scan(*entities: dict[str, object]) -> dict[str, Points]:
    """The index over one message, in a context of its own."""
    return shapes_by_trip(message(*entities), context())


def test_a_trip_properties_shape_id_reaches_its_shape():
    found = scan(entity("a", trip_update=properties()), entity("b", shape=SHAPE))

    assert found == {"T1": SWAPPED}


def test_the_shape_may_come_first():
    """Entity order is the feed's business, not this module's."""
    found = scan(entity("a", shape=SHAPE), entity("b", trip_update=properties()))

    assert found == {"T1": SWAPPED}


def test_trip_properties_trip_id_wins_over_the_descriptors():
    """For a NEW trip it is the id the trip is published under, while the
    descriptor may still name the trip being replaced."""
    renaming = {
        "trip": {"trip_id": "OLD"},
        "trip_properties": {"shape_id": "RT1", "trip_id": "NEW"},
    }
    found = scan(entity("a", trip_update=renaming), entity("b", shape=SHAPE))

    assert found == {"NEW": SWAPPED}


def test_selected_trips_name_several_at_once():
    modifications = {"selected_trips": [{"trip_ids": ["T1", "T2"], "shape_id": "RT1"}]}
    found = scan(entity("a", trip_modifications=modifications), entity("b", shape=SHAPE))

    assert found == {"T1": SWAPPED, "T2": SWAPPED}


def test_a_claim_on_a_shape_nobody_published_resolves_to_nothing():
    assert scan(entity("a", trip_update=properties())) == {}


def test_a_shape_nobody_claims_reaches_no_trip():
    assert scan(entity("a", shape=SHAPE)) == {}


def test_a_polyline_that_stopped_early_is_not_a_path():
    """A truncated shape is S040's finding. Measuring against the part that
    decoded would report a vehicle against a path its feed never published."""
    broken = {"shape_id": "RT1", "encoded_polyline": "_p~iF"}

    assert scan(entity("a", trip_update=properties()), entity("b", shape=broken)) == {}


def test_a_shape_with_no_points_reaches_no_trip():
    """The empty string is a clean decode of zero points rather than a failure,
    and the join drops it anyway: a shape with no points is not a path, and a
    caller left holding one would have to compare a distance that does not
    exist. P015 falls back to `shapes.txt` because of this line."""
    empty = {"shape_id": "RT1", "encoded_polyline": ""}

    assert scan(entity("a", trip_update=properties()), entity("b", shape=empty)) == {}


def test_the_cycle_is_scanned_from_every_role_of_it():
    """A `Shape` published in the TripUpdates file, read from the
    VehiclePositions message of the same cycle, whose role is not the host.

    The host is `-tu` here, so before the cycle view was split from the token
    that says which message reports, this fell back to scanning the
    VehiclePositions message and found nothing.
    """
    updates = message(entity("a", trip_update=properties()), entity("b", shape=SHAPE))
    positions = message(entity("c", vehicle={"vehicle": {"id": "1"}}))
    cycle = cycle_of({"tu": updates, "vp": positions})

    assert shapes_by_trip(positions, context(role="vp", cycle=cycle)) == {"T1": SWAPPED}


def test_two_rules_asking_one_message_scan_it_once(monkeypatch):
    """The memo. P015 is the only reader today and it asks once, but the module
    is a shared one and the next reader must not pay for a second traversal."""
    runs = sharing(monkeypatch, realtime_shapes, "_build")
    ctx = context()
    one = message(entity("a", trip_update=properties()), entity("b", shape=SHAPE))

    assert shapes_by_trip(one, ctx) == {"T1": SWAPPED}
    assert shapes_by_trip(one, ctx) == {"T1": SWAPPED}

    assert len(runs) == 1
