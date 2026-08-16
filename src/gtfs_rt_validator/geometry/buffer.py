"""Containment in the JTS 1.13 planar buffer of a trip shape, for E029.

Upstream's `GtfsMetadata.getBufferedTripShape` delegates to
`JtsGeometry.getBuffered`, which delegates to
`com.vividsolutions.jts.geom.Geometry.buffer(TRIP_BUFFER_DEGREES)` on a
`LineString` of shape points in raw lon/lat degrees, and the containment test
reduces to `geom.disjoint(point) ? DISJOINT : CONTAINS`.

This module reproduces JTS's construction rather than the geometry it
approximates, because the approximation is what defines the answer. Two effects
move the boundary far more than floating point does, in opposite directions:

* Round joins and caps are drawn with 8 chord segments per quadrant, and a chord
  lies inside its arc, so near a convex vertex the polygon falls short of the
  true offset by up to `1 - cos(pi/32)`, about 0.48% of the distance.
* Before offsetting, `BufferInputLineSimplifier` deletes shallow concave
  vertices whose deviation is under `distance / 100`, so near a concave vertex
  the polygon reaches past the true offset by up to 1% of the distance.

Neither is reproducible by a distance-to-polyline test. What is reproduced here
is `OffsetCurveBuilder.getLineCurve`, vertex for vertex, checked against the
real jar by `tools/diff_geometry_against_java.py` and `tools/DumpJtsBuffer.java`.

Stdlib only, by this project's no-third-party-runtime rule. Ported from the JTS
1.13 sources (`com.vividsolutions:jts:1.13`, the pre-LocationTech groupId
upstream's pom.xml pins); `org.locationtech.jts` is a different artifact and is not equivalent.

The port is split three ways by concern, and only this module is meant to be
imported from outside `geometry`: `_predicates.py` holds the JTS primitives (the
orientation test, the line intersector, the distances), `_offset_curve.py` holds
the input simplifier and the segment generator along with the `BufferParameters`
constants re-exported below, and what stays here is the public entry point,
`OffsetCurveBuilder.getLineCurve` itself, and the containment tally.
"""

from __future__ import annotations

from collections.abc import Sequence

from gtfs_rt_validator.geometry._offset_curve import (
    CLOSING_SEG_LENGTH_FACTOR,
    CURVE_VERTEX_SNAP_DISTANCE_FACTOR,
    FILLET_ANGLE_QUANTUM,
    INSIDE_TURN_VERTEX_SNAP_DISTANCE_FACTOR,
    OFFSET_SEGMENT_SEPARATION_FACTOR,
    QUADRANT_SEGMENTS,
    SIMPLIFY_FACTOR,
    _SegmentGenerator,
    _simplify,
)
from gtfs_rt_validator.geometry._predicates import Point, _sign_of_det2x2

# The constants above are re-exported rather than defined here: they are the
# measured `BufferParameters` defaults, they are read by the curve builder, and
# callers and tests import them from this module.
__all__ = [
    "CLOSING_SEG_LENGTH_FACTOR",
    "CURVE_VERTEX_SNAP_DISTANCE_FACTOR",
    "FILLET_ANGLE_QUANTUM",
    "INSIDE_TURN_VERTEX_SNAP_DISTANCE_FACTOR",
    "OFFSET_SEGMENT_SEPARATION_FACTOR",
    "QUADRANT_SEGMENTS",
    "SIMPLIFY_FACTOR",
    "Point",
    "within_buffered_shape",
]


def within_buffered_shape(
    shape: Sequence[Point],
    lon: float,
    lat: float,
    distance_degrees: float,
) -> bool:
    """Is `(lon, lat)` inside the JTS buffer of `shape` at `distance_degrees`?

    `shape` is lon/lat degrees in `(x, y)` order, matching spatial4j's
    `pointXY(lon, lat)` and this function's own argument order. A point exactly
    on the buffer boundary counts as inside, because upstream's test is
    `not disjoint`, not `contains`.

    The geography this reproduces is wrong, and reproducing it is the point. The
    buffer is applied to degrees with no latitude correction, so north-south it
    spans about 200 m at `TRIP_BUFFER_DEGREES` while east-west it spans about
    `200 * cos(lat)` m: about 176.6 m at 28 N, about 129 m at 50 N. The E029
    occurrence text still reads "more than 200.0 meters". That is upstream being
    wrong; compat reproduces it deliberately, and any correction belongs in the
    tier that is allowed to disagree with upstream.

    Raises `ValueError` for a one-point shape: JTS refuses to build a
    `LineString` from a single coordinate ("Invalid number of points in
    LineString (found 1 - must be 0 or >= 2)"), so upstream dies there rather
    than answering. An empty shape is an empty `LineString`, whose buffer is
    empty and therefore disjoint from everything.
    """
    if len(shape) == 1:
        raise ValueError("a one-point shape is not a LineString; JTS refuses to build one")
    if not shape or distance_degrees <= 0.0:
        # OffsetCurveSetBuilder.addLineString: a zero or negative width buffer of
        # a line is empty, and an empty geometry is disjoint from every point.
        return False
    ring = _buffer_curve(shape, distance_degrees)
    if len(ring) < 2:
        return False
    return _covered_by_ring(ring, (float(lon), float(lat)))


def _buffer_curve(shape: Sequence[Point], distance: float) -> list[Point]:
    """The raw offset curve, exactly `OffsetCurveBuilder.getLineCurve`.

    Not noded and usually self-intersecting, which is what JTS itself produces
    before handing the curve to the overlay. `_covered_by_ring` reads winding
    numbers off it instead of running the overlay; the differential harness
    compares both this curve and the containment answers against the jar.
    """
    pts = _remove_repeated_points(shape)
    gen = _SegmentGenerator(distance)
    if len(pts) <= 1:
        # computePointCurve, CAP_ROUND branch.
        gen.create_circle(pts[0])
        return gen.coordinates
    _compute_line_buffer_curve(pts, gen, distance)
    return gen.coordinates


def _compute_line_buffer_curve(pts: list[Point], gen: _SegmentGenerator, distance: float) -> None:
    """`OffsetCurveBuilder.computeLineBufferCurve`.

    Both sides are offset LEFT, the right-hand one by walking the line
    backwards, and each side is simplified with its own signed tolerance, so the
    two sides can be generated from different vertex sets.
    """
    dist_tol = distance / SIMPLIFY_FACTOR

    simp1 = _simplify(pts, dist_tol)
    n1 = len(simp1) - 1
    gen.init_side_segments(simp1[0], simp1[1])
    for i in range(2, n1 + 1):
        gen.add_next_segment(simp1[i])
    gen.add_last_segment()
    gen.add_line_end_cap(simp1[n1 - 1], simp1[n1])

    simp2 = _simplify(pts, -dist_tol)
    n2 = len(simp2) - 1
    gen.init_side_segments(simp2[n2], simp2[n2 - 1])
    for i in range(n2 - 2, -1, -1):
        gen.add_next_segment(simp2[i])
    gen.add_last_segment()
    gen.add_line_end_cap(simp2[1], simp2[0])

    gen.close_ring()


def _remove_repeated_points(shape: Sequence[Point]) -> list[Point]:
    """`CoordinateArrays.removeRepeatedPoints`, applied by `OffsetCurveSetBuilder`."""
    out: list[Point] = []
    for p in shape:
        pt = (float(p[0]), float(p[1]))
        if not out or out[-1] != pt:
            out.append(pt)
    return out


def _covered_by_ring(ring: list[Point], q: Point) -> bool:
    """Is `q` on or inside the raw offset curve?

    JTS gets here by noding the curve, labelling each resulting edge with a
    depth, keeping the edges that bound depth of at least 1, assembling those
    into polygon rings, and finally running `RayCrossingCounter` over the ring
    that comes out. Depth is the winding number of the curve, so this counts
    crossings of the raw curve instead of building the polygon: a point with
    non-zero winding is interior, and a point on the curve is on the boundary,
    which upstream's `not disjoint` test counts as inside.

    The per-segment arithmetic below is `RayCrossingCounter.countSegment`
    unchanged, including its early exits and its translation of the segment onto
    the query point. Only the tally differs: JTS counts crossings and takes the
    parity, which is right for a simple polygon ring and wrong for a raw offset
    curve, where a region covered twice must stay inside.
    """
    winding = 0
    for i in range(len(ring) - 1):
        p1 = ring[i]
        p2 = ring[i + 1]
        if p1[0] < q[0] and p2[0] < q[0]:
            continue
        if q == p2:
            return True
        if p1[1] == q[1] and p2[1] == q[1]:
            # Horizontal segments are never counted, only tested for the point
            # lying on them.
            if min(p1[0], p2[0]) <= q[0] <= max(p1[0], p2[0]):
                return True
            continue
        # An upward edge owns its start vertex and a downward edge its end
        # vertex, so a vertex on the ray is counted exactly once.
        if not ((p1[1] > q[1] and p2[1] <= q[1]) or (p2[1] > q[1] and p1[1] <= q[1])):
            continue
        x1 = p1[0] - q[0]
        y1 = p1[1] - q[1]
        x2 = p2[0] - q[0]
        y2 = p2[1] - q[1]
        sign = _sign_of_det2x2(x1, y1, x2, y2)
        if sign == 0:
            return True
        upward = y2 > y1
        if not upward:
            sign = -sign
        if sign > 0:
            winding += 1 if upward else -1
    return winding != 0
