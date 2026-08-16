"""The feed P015's tests measure against, and the polyline encoder they need.

Split out of `tests/test_rule_p015.py` so neither file grows past the size hook.
What is here is the *fixture*, not an assertion: a static feed at latitude 60, a
VehiclePosition builder that places a vehicle a stated number of degrees north of
that feed's shape, and an encoder for the realtime `Shape` cases.

**Latitude 60 is the whole design.** E029 buffers 0.0017986 degrees in raw
degrees, so north-south it clears everything within 0.0017986 times the length of
a degree of latitude: 198.9 metres at the equator and 200.39 metres here. The
band `:120` describes and E029 does not reach therefore exists only above about
48.3 degrees, and at 60 it is the shell between 200 and 200.39 metres. The test
module's docstring carries the three measured offsets.
"""

from __future__ import annotations

__all__ = [
    "BEYOND_E029",
    "DETOUR",
    "INSIDE_200",
    "IN_BAND",
    "LAT",
    "LON",
    "REDUCED_SERVICE",
    "at",
    "declares",
    "encode_polyline",
    "shape",
    "tables",
]

#: Where the fixture feed lives.
LAT, LON = 60.0, 10.0

#: Three offsets north of the shape, measured against
#: `geometry/buffer.within_buffered_shape` and
#: `_shared/geodesic.distance_to_polyline` rather than derived from a formula.
IN_BAND, INSIDE_200, BEYOND_E029 = 0.0017980, 0.0017900, 0.0025

#: `Alert.Effect`, by number, which is the same number under both schemas.
DETOUR, REDUCED_SERVICE = 4, 2

#: The format's fixed precision, and the encoder's continuation bit.
SCALE, CONTINUATION, OFFSET = 1e5, 0x20, 63


def encode_polyline(points: list[tuple[float, float]]) -> str:
    """`(latitude, longitude)` pairs, in Google's encoded polyline format.

    The inverse of `_shared/polyline.decode_polyline`, written here because
    nothing ships an encoder and a realtime `Shape` has to carry one of these.
    `test_the_fixture_encoder_round_trips` pins it against the real decoder, so
    a fixture built with it is one the shipped code agrees about.
    """
    out: list[str] = []
    previous = (0, 0)
    for point in points:
        scaled = (round(point[0] * SCALE), round(point[1] * SCALE))
        for value, before in zip(scaled, previous, strict=True):
            zigzag = (value - before) << 1
            zigzag = ~zigzag if zigzag < 0 else zigzag
            while zigzag >= CONTINUATION:
                out.append(chr((CONTINUATION | (zigzag & 0x1F)) + OFFSET))
                zigzag >>= 5
            out.append(chr(zigzag + OFFSET))
        previous = scaled
    return "".join(out)


def tables() -> dict[str, list[dict[str, str]]]:
    """One route, two trips, and a four-point shape along the parallel at 60.

    Four points because the feed-wide shape gate is `shapePoints.size() > 3`;
    below it there is no shape data at all and E029 is disabled, which would make
    every case the same case. **T2 declares no `shape_id`**, so it is the trip
    whose only geometry can come from a realtime `Shape`.
    """
    return {
        "agency.txt": [
            {
                "agency_id": "A1",
                "agency_name": "Test Transit",
                "agency_url": "https://example.com",
                "agency_timezone": "Europe/Oslo",
            }
        ],
        "stops.txt": [
            {"stop_id": "S1", "stop_name": "First", "stop_lat": "60.0", "stop_lon": "10.0"},
            {"stop_id": "S2", "stop_name": "Second", "stop_lat": "60.0", "stop_lon": "10.003"},
        ],
        "routes.txt": [
            {"route_id": "R1", "agency_id": "A1", "route_short_name": "1", "route_type": "3"}
        ],
        "trips.txt": [
            {"trip_id": "T1", "route_id": "R1", "service_id": "SVC1", "shape_id": "SH1"},
            {"trip_id": "T2", "route_id": "R1", "service_id": "SVC1", "shape_id": ""},
        ],
        "stop_times.txt": [
            {
                "trip_id": trip_id,
                "arrival_time": "08:00:00",
                "departure_time": "08:00:00",
                "stop_id": stop_id,
                "stop_sequence": str(sequence),
            }
            for trip_id in ("T1", "T2")
            for sequence, stop_id in enumerate(["S1", "S2"], start=1)
        ],
        "shapes.txt": [
            {
                "shape_id": "SH1",
                "shape_pt_lat": "60.0",
                "shape_pt_lon": f"{LON + 0.001 * step:.3f}",
                "shape_pt_sequence": str(step + 1),
            }
            for step in range(4)
        ],
    }


def at(dlat: float, lon: float = LON + 0.0015, trip_id: str = "T1") -> dict[str, object]:
    """A VehiclePosition `dlat` degrees north of the shape, over its midpoint.

    Over the *interior* of a segment rather than over a vertex, because JTS
    approximates a buffer's round joins with chords and offsets the straight
    parts exactly. Above a vertex the boundary would be a chord and the band's
    edge would depend on how many quadrant segments the port drew.
    """
    return {
        "trip": {"trip_id": trip_id, "route_id": "R1"},
        "vehicle": {"id": "1"},
        "position": {"latitude": LAT + dlat, "longitude": lon},
    }


def shape(shape_id: str, points: list[tuple[float, float]]) -> dict[str, object]:
    """A `Shape` entity's payload, carrying `points` as an encoded polyline."""
    return {"shape_id": shape_id, "encoded_polyline": encode_polyline(points)}


def declares(shape_id: str, trip_id: str = "T2") -> dict[str, object]:
    """A TripUpdate binding `trip_id` to a realtime shape through TripProperties."""
    return {"trip": {"trip_id": trip_id}, "trip_properties": {"shape_id": shape_id}}
