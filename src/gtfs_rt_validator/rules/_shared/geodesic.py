"""Distance in metres from a point to a polyline, on the WGS-84 ellipsoid. P015.

`:120` of the Best Practices says 200 **metres**, and this project has no way to
measure metres. `geometry/buffer.py` and `geometry/bbox.py` work in **degrees**,
planar and with no latitude correction, because they reproduce JTS 1.13 and
spatial4j 0.6 so that E029 matches the jar byte for byte: at 45 degrees north
E029's "200 meters" is 141 metres east to west and at 60 degrees it is 100. That
is upstream's behaviour and reproducing it is the point, which makes those two
modules the wrong tool here **by construction** rather than by accident. Nothing
in this module reaches the compat path, and nothing on the compat path may come
to read it: P015 is the only rule that does, it is a `practice` rule, and the
registry keeps the cited tiers out of compat entirely.

## What it computes, and how far off it is

The two points are converted to earth-centred coordinates on the WGS-84
ellipsoid and then into a local east-north plane whose origin is the **query
point**, after which the point-to-segment problem is the planar one. There is no
spherical earth anywhere in this: the ellipsoid's own prime-vertical radius of
curvature is used at each point's own latitude, so nothing here assumes a radius.

The one approximation left is that the tangent plane is flat where the ellipsoid
is not, which shortens a long distance by about `s**3 / (6 * R**2)`. **Measured**
against Vincenty's inverse solution, over a grid of latitudes from 80 south to 80
north, all 24 bearings, and both near the prime meridian and across the
antimeridian:

| separation | worst error |
|---|---|
| 200 m | 0.24 micrometres |
| 1 km | 4.2 micrometres |
| 10 km | 4.2 mm |
| 100 km | 4.3 m |
| 1000 km | 5.9 km |

So it is exact for anything a transit vehicle is doing near a 200-metre
threshold and it is not a general-purpose long-range geodesic. The bound is
pinned by `tests/test_shared_geodesic.py`, which carries its own Vincenty
implementation as the oracle rather than taking these numbers on trust; the
error grows as the cube of the separation, so a reader can extrapolate the row
they need and then go and measure it.

The segment itself contributes almost nothing to that error. A geodesic between
two vertices bows away from the straight line this draws between them, and the
worst offset measured the same way is 3.3 micrometres for a segment **100 km
long**. GTFS shape points are metres apart, so this term is not worth a sentence
except to say it was checked.

## Two conventions, and both are the project's own

Coordinates are `(lon, lat)` pairs and the scalar arguments are in that order
too, matching `geometry/buffer.within_buffered_shape` and `static/_tables.Point`
and every other coordinate pair here. Degrees, not radians.

The antimeridian needs no special case and gets none. Earth-centred coordinates
are global, so a longitude of 179.9995 and one of -179.9995 are 111 metres
apart because they are, not because a wrapping rule was remembered.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "WGS84_FLATTENING",
    "WGS84_SEMI_MAJOR_METERS",
    "distance_to_point",
    "distance_to_polyline",
]

#: WGS-84's defining parameters, `NGA.STND.0036_1.0.0_WGS84`. The same ellipsoid
#: every GTFS coordinate is expressed on.
WGS84_SEMI_MAJOR_METERS = 6378137.0
WGS84_FLATTENING = 1 / 298.257223563

#: First eccentricity squared, `f * (2 - f)`, written that way rather than as
#: `1 - (b/a)**2` because it loses no precision to cancellation.
_E2 = WGS84_FLATTENING * (2 - WGS84_FLATTENING)


def distance_to_point(point: tuple[float, float], lon: float, lat: float) -> float:
    """Metres between `point` and `(lon, lat)`. Both are `(lon, lat)` degrees."""
    east, north = _east_north(point, lon, lat)
    return math.hypot(east, north)


def distance_to_polyline(
    points: Sequence[tuple[float, float]], lon: float, lat: float
) -> float | None:
    """Metres from `(lon, lat)` to the nearest point of the polyline, or `None`.

    `None` means the polyline has no points, which is a shape that decoded to
    nothing rather than a shape that is far away. It is `None` and not `inf`
    on purpose: `inf` compares greater than any threshold, so a caller that
    forgot to check would report every vehicle on a feed whose shapes failed to
    decode. `None` raises a `TypeError` at the comparison instead, which is the
    loud version of the same mistake.

    A one-point polyline is that point's distance. Beyond either end of a
    segment the answer is the distance to that **endpoint**, not to the infinite
    line the segment lies on, which is what makes this a distance to the shape
    rather than to its extension.
    """
    if not points:
        return None
    if len(points) == 1:
        return distance_to_point(points[0], lon, lat)
    projected = [_east_north(point, lon, lat) for point in points]
    return min(
        _origin_to_segment(projected[index], projected[index + 1])
        for index in range(len(projected) - 1)
    )


def _east_north(point: tuple[float, float], lon: float, lat: float) -> tuple[float, float]:
    """`point` in metres east and north of `(lon, lat)`, on the tangent plane.

    The up component is computed and dropped, and dropping it is a real choice
    with a measured cost. Keeping it would answer the straight line through the
    ellipsoid, which is the more accurate of the two for a *pair* of points: on
    the equator at 100 km the chord is 1.02 m short of the geodesic where this
    projection is 4.10 m short. It is dropped anyway, because the question here
    is the nearest point of a *segment*, and the nearest point of a chord
    through the rock is a place no vehicle can be. Two dimensions is what makes
    `_origin_to_segment` mean what it says, and at the ranges P015 works at both
    errors round to zero.
    """
    x, y, z = _earth_centred(point[0], point[1])
    x0, y0, z0 = _earth_centred(lon, lat)
    dx, dy, dz = x - x0, y - y0, z - z0
    phi, lam = math.radians(lat), math.radians(lon)
    sin_phi, cos_phi = math.sin(phi), math.cos(phi)
    sin_lam, cos_lam = math.sin(lam), math.cos(lam)
    east = -sin_lam * dx + cos_lam * dy
    north = -sin_phi * cos_lam * dx - sin_phi * sin_lam * dy + cos_phi * dz
    return east, north


def _earth_centred(lon: float, lat: float) -> tuple[float, float, float]:
    """Geodetic degrees to earth-centred earth-fixed metres, at zero height.

    Height is zero for every coordinate this project sees: GTFS carries no
    altitude for a stop or a shape point, and `VehiclePosition.Position` has an
    `odometer` and a `bearing` but nothing vertical either. So a vehicle on a
    viaduct is measured as though it were on the ellipsoid, which costs the
    horizontal distance nothing.
    """
    phi, lam = math.radians(lat), math.radians(lon)
    sin_phi, cos_phi = math.sin(phi), math.cos(phi)
    prime_vertical = WGS84_SEMI_MAJOR_METERS / math.sqrt(1 - _E2 * sin_phi * sin_phi)
    return (
        prime_vertical * cos_phi * math.cos(lam),
        prime_vertical * cos_phi * math.sin(lam),
        prime_vertical * (1 - _E2) * sin_phi,
    )


def _origin_to_segment(start: tuple[float, float], end: tuple[float, float]) -> float:
    """Planar distance from `(0, 0)` to the segment, which is where the query
    point sits by construction.

    `t` is clamped to `[0, 1]`, and that clamp is the whole of the
    "beyond the end" behaviour: unclamped this would answer the distance to the
    infinite line the segment lies on, which is never larger and is often much
    smaller. A vehicle a kilometre past the end of its shape, in line with the
    last two points, would measure as being on the shape.
    """
    dx, dy = end[0] - start[0], end[1] - start[1]
    span = dx * dx + dy * dy
    if span == 0:
        return math.hypot(start[0], start[1])
    t = -(start[0] * dx + start[1] * dy) / span
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(start[0] + t * dx, start[1] + t * dy)
