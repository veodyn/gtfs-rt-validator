"""P015: a vehicle more than 200 metres from its shape that E029 let through.

The fixture feed sits at **latitude 60**, and that is the whole design of this
module rather than a taste in coordinates. E029 buffers `TRIP_BUFFER_DEGREES`,
0.0017986, in raw degrees: north-south that is `0.0017986` times the length of a
degree of latitude, which is 198.9 metres at the equator and 200.39 metres at 60
degrees north. So the set of positions E029 clears and `:120` does not is empty
below about 48.3 degrees and is the shell between 200 m and 200.39 m at 60. The
numbers below were measured against `geometry/buffer.within_buffered_shape` and
`_shared/geodesic.distance_to_polyline`, not derived from that paragraph:

    dlat 0.0017900  ->  199.43 m, inside E029's buffer
    dlat 0.0017980  ->  200.32 m, inside E029's buffer   <- the band
    dlat 0.0018100  ->  201.66 m, outside                <- E029's

**The occurrences below say 200.2 and not 200.32, and that is the wire rather
than a rounding.** `Position.latitude` and `.longitude` are protobuf `float`, so
a fixture encoded and decoded through `proto/` carries the nearest float32 to
60.0017980, which is 60.00179672 and about a tenth of a metre lower down. Every
expected string here was read off a run rather than computed from the table.

`test_a_position_e029_clears_and_the_document_does_not_is_reported` and
`test_a_position_e029_reports_is_not_this_rules` are the pair that make the
declared overlap with E029 true: the first asserts E029 is silent where this
rule fires, the second asserts this rule is silent where E029 fires. Neither is
a paragraph.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.rules._shared.polyline import decode_polyline
from gtfs_rt_validator.rules.practice.p015 import check
from gtfs_rt_validator.rules.upstream.e029 import check as e029_check
from p015fixtures import (
    BEYOND_E029,
    DETOUR,
    IN_BAND,
    INSIDE_200,
    LAT,
    LON,
    REDUCED_SERVICE,
    at,
    declares,
    encode_polyline,
    shape,
    tables,
)
from specfixtures import cycle_of, entity, feed_context, message, prefixes


def run(tmp_path, *entities, **overrides):
    return check(message(*entities), feed_context(tmp_path, tables(), **overrides))


def reported(distance: str, source: str = "shapes.txt", trip_id: str = "T1") -> str:
    return (
        f"trip_id {trip_id} is {distance} meters from the trip shape in {source}, which is "
        f"more than 200, and no alert with an effect of DETOUR names the trip"
    )


def test_the_fixture_encoder_round_trips():
    """The helper above against the shipped decoder, at the format's own
    precision. Without this every realtime-shape fixture below would be
    asserting against a second, unchecked implementation of the algorithm."""
    points = [(60.00180, 10.00100), (60.00180, 10.00200), (59.99000, 9.99000)]

    assert decode_polyline(encode_polyline(points)).points == tuple(points)


def test_a_position_e029_clears_and_the_document_does_not_is_reported(tmp_path):
    """The band, and both halves of it in one test. 200.32 metres is more than
    the 200 `:120` asks for and is inside the 0.0017986-degree buffer E029
    applies, which at this latitude is 200.39 metres."""
    found = run(tmp_path, entity(vehicle=at(IN_BAND)))
    context = feed_context(tmp_path, tables())

    assert prefixes(found) == [reported("200.2")]
    assert prefixes(e029_check(message(entity(vehicle=at(IN_BAND))), context)) == []


def test_a_position_inside_200_metres_is_silent(tmp_path):
    """The conformant twin, eight ten-thousandths of a degree lower down."""
    assert prefixes(run(tmp_path, entity(vehicle=at(INSIDE_200)))) == []


def test_the_boundary_is_satisfied_by_exactly_200_metres(tmp_path):
    """ "should be within 200 meters" is satisfied at 200, so the comparison is
    strict. 0.00179455 degrees measures 200.0000 metres here."""
    assert prefixes(run(tmp_path, entity(vehicle=at(0.00179455)))) == []


def test_a_position_e029_reports_is_not_this_rules(tmp_path):
    """The other direction of the declared overlap: no vehicle is reported twice.
    E029 owns everything outside its own buffer, and it is a compat byte
    contract, so this rule stands in its nest rather than beside it."""
    found = run(tmp_path, entity(vehicle=at(BEYOND_E029)))
    context = feed_context(tmp_path, tables())

    assert prefixes(found) == []
    assert len(list(e029_check(message(entity(vehicle=at(BEYOND_E029))), context))) == 1


def test_a_vehicle_outside_the_agency_box_is_e028s(tmp_path):
    """E028 fired, so E029 was never evaluated and this rule was never reached.
    Measuring a vehicle in another country against a trip shape is the double
    report `e029.py`'s docstring warns a naive port into."""
    found = run(tmp_path, entity(vehicle=at(0.0, lon=LON + 5.0)))
    context = feed_context(tmp_path, tables())

    assert prefixes(found) == []
    assert len(list(e029_check(message(entity(vehicle=at(0.0, lon=LON + 5.0))), context))) == 0


def test_a_position_off_the_earth_is_e026s(tmp_path):
    """A latitude of 91 is not a place, so a distance from it is a number rather
    than a measurement."""
    assert prefixes(run(tmp_path, entity(vehicle=at(31.0)))) == []


def test_a_detour_alert_for_the_trip_exempts_it(tmp_path):
    """The clause's own exemption, and the reason it is spelled out in the
    occurrence text: the finding is "far from the shape *and* nobody said why"."""
    found = run(
        tmp_path,
        entity("a", vehicle=at(IN_BAND)),
        entity("b", alert={"effect": DETOUR, "informed_entity": [{"trip": {"trip_id": "T1"}}]}),
    )

    assert prefixes(found) == []


def test_a_detour_alert_naming_another_trip_does_not_exempt_it(tmp_path):
    found = run(
        tmp_path,
        entity("a", vehicle=at(IN_BAND)),
        entity("b", alert={"effect": DETOUR, "informed_entity": [{"trip": {"trip_id": "T9"}}]}),
    )

    assert prefixes(found) == [reported("200.2")]


def test_an_alert_with_another_effect_does_not_exempt_it(tmp_path):
    found = run(
        tmp_path,
        entity("a", vehicle=at(IN_BAND)),
        entity(
            "b",
            alert={"effect": REDUCED_SERVICE, "informed_entity": [{"trip": {"trip_id": "T1"}}]},
        ),
    )

    assert prefixes(found) == [reported("200.2")]


def test_a_detour_alert_in_another_role_of_the_cycle_exempts_it(tmp_path):
    """Wider than E029, which scans its own message only. An alerts feed is a
    separate file in modern mode, so a rule reading only its own message would
    report every detoured vehicle in a `-vp -sa` run.

    The cycle carries `-tu` as well, so the VehiclePositions message is **not**
    its host. That is the point of the fixture: the exemption has to survive the
    role that reports for the cycle being somebody else, because `-tu -vp -sa`
    is the layout an agency publishing three files actually has.
    """
    alerts = message(
        entity(alert={"effect": DETOUR, "informed_entity": [{"trip": {"trip_id": "T1"}}]})
    )
    positions = message(entity(vehicle=at(IN_BAND)))
    cycle = cycle_of({"tu": message(), "vp": positions, "sa": alerts})
    context = feed_context(tmp_path, tables(), role="vp", cycle=cycle)

    assert cycle.host_role == "tu"
    assert prefixes(check(positions, context)) == []


def test_a_trip_with_no_static_shape_is_measured_against_a_realtime_one(tmp_path):
    """What E029 cannot do at all: `Shape` postdates the 2015 schema, and T2 has
    no `shape_id` in `trips.txt` for `getBufferedTripShape` to find."""
    found = run(
        tmp_path,
        entity("a", vehicle=at(BEYOND_E029, lon=LON + 0.011, trip_id="T2")),
        entity("b", trip_update=declares("RT1")),
        entity("c", shape=shape("RT1", [(LAT, LON + 0.010), (LAT, LON + 0.012)])),
    )

    assert prefixes(found) == [reported("278.4", source="a realtime Shape entity", trip_id="T2")]


def test_a_realtime_shape_is_preferred_over_shapes_txt(tmp_path):
    """A trip that publishes a shape has said that `shapes.txt` is not its path.
    This vehicle is in the band against SH1 and on RT1, and the rule is silent."""
    found = run(
        tmp_path,
        entity("a", vehicle=at(IN_BAND)),
        entity("b", trip_update=declares("RT1", trip_id="T1")),
        entity(
            "c", shape=shape("RT1", [(LAT + IN_BAND, LON + 0.001), (LAT + IN_BAND, LON + 0.002)])
        ),
    )

    assert prefixes(found) == []


def test_trip_modifications_bind_a_shape_too(tmp_path):
    """`TripModifications.SelectedTrips` carries `trip_ids` and a `shape_id`,
    which is the other way a realtime shape reaches a trip."""
    modifications = {"selected_trips": [{"trip_ids": ["T2"], "shape_id": "RT1"}]}
    found = run(
        tmp_path,
        entity("a", vehicle=at(BEYOND_E029, lon=LON + 0.011, trip_id="T2")),
        entity("b", trip_modifications=modifications),
        entity("c", shape=shape("RT1", [(LAT, LON + 0.010), (LAT, LON + 0.012)])),
    )

    assert prefixes(found) == [reported("278.4", source="a realtime Shape entity", trip_id="T2")]


def test_a_realtime_shape_that_decodes_to_nothing_falls_back_to_the_static_one(tmp_path):
    """`distance_to_polyline` answers `None` for an empty polyline rather than
    `inf`, precisely so this case cannot become a silent report of every vehicle
    in the feed. An unusable realtime shape leaves `shapes.txt` as the source."""
    found = run(
        tmp_path,
        entity("a", vehicle=at(IN_BAND)),
        entity("b", trip_update=declares("RT1", trip_id="T1")),
        entity("c", shape={"shape_id": "RT1", "encoded_polyline": ""}),
    )

    assert prefixes(found) == [reported("200.2")]


def test_a_trip_with_no_shape_anywhere_is_out_of_scope(tmp_path):
    """T2 has no `shape_id` and no realtime `Shape` names it. There is nothing
    to be 200 metres from."""
    found = run(tmp_path, entity(vehicle=at(BEYOND_E029, trip_id="T2")))

    assert prefixes(found) == []


def test_a_vehicle_naming_no_trip_is_out_of_scope(tmp_path):
    position = {
        "vehicle": {"id": "1"},
        "position": {"latitude": LAT + BEYOND_E029, "longitude": LON},
    }

    assert prefixes(run(tmp_path, entity(vehicle=position))) == []


def test_a_vehicle_with_no_position_is_out_of_scope(tmp_path):
    found = run(tmp_path, entity(vehicle={"trip": {"trip_id": "T1"}, "vehicle": {"id": "1"}}))

    assert prefixes(found) == []


def test_the_occurrence_locates_the_vehicle_and_names_the_distance(tmp_path):
    (found,) = run(tmp_path, entity("a", alert={}), entity("b", vehicle=at(IN_BAND)))

    assert found.rule_id == "P015"
    assert found.context["entityPath"] == "entity[1].vehicle"
    assert found.context["tripId"] == "T1"
    assert found.context["distanceMeters"] == pytest.approx(200.2, abs=0.05)
    assert found.context["shapeSource"] == "shapes.txt"


def test_two_vehicles_report_separately(tmp_path):
    found = run(
        tmp_path,
        entity("a", vehicle=at(IN_BAND)),
        entity("b", vehicle=at(INSIDE_200)),
        entity("c", vehicle=at(IN_BAND, lon=LON + 0.0025)),
    )

    assert [one.context["entityPath"] for one in found] == [
        "entity[0].vehicle",
        "entity[2].vehicle",
    ]
