"""The JTS predicates the buffer construction stands on, ported from JTS 1.13.

Split out of `buffer.py`, which holds the module docstring for the reproduction
as a whole and drives what is here: `CGAlgorithms.orientationIndex` and
`distancePointLine`, `RobustDeterminant.signOfDet2x2`, `computeOffsetSegment`,
and as much of `RobustLineIntersector` as the offset curve generator reads.
Nothing in this module knows what a buffer is; each function is a primitive over
points, and each is measured against the jar through the callers in `buffer.py`.

Stdlib only, by this project's no-third-party-runtime rule, enforced for this
module too by
`tests/test_buffer.py::test_buffer_imports_only_the_standard_library`.
"""

from __future__ import annotations

import math
from fractions import Fraction

Point = tuple[float, float]

_CLOCKWISE = -1
_COUNTERCLOCKWISE = 1

# Error bound for the floating-point filter in `_orientation_index`. 3 * 2**-53,
# the standard bound for a 2x2 determinant of differences of doubles.
_ORIENTATION_FILTER = 3.3306690738754716e-16


def _offset_segment(p0: Point, p1: Point, side_sign: int, distance: float) -> tuple[Point, Point]:
    """`computeOffsetSegment`. A zero-length segment yields NaN, as it does in Java."""
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    length = math.sqrt(dx * dx + dy * dy)
    ux = _div(side_sign * distance * dx, length)
    uy = _div(side_sign * distance * dy, length)
    return ((p0[0] - uy, p0[1] + ux), (p1[0] - uy, p1[1] + ux))


def _div(a: float, b: float) -> float:
    """Java's `/` on doubles: 0/0 is NaN and x/0 is signed infinity, never a raise."""
    if b != 0.0:
        return a / b
    if a == 0.0 or a != a:
        return math.nan
    return math.copysign(math.inf, a)


def _dist(a: Point, b: Point) -> float:
    """`Coordinate.distance`. Not `math.hypot`, which is more accurate than Java is.

    Every threshold in the generator is a comparison against this, so a value
    that rounds differently can take a different branch and change the curve.
    """
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return math.sqrt(dx * dx + dy * dy)


# ---------------------------------------------------------------------------
# RobustLineIntersector, only as far as the generator uses it
# ---------------------------------------------------------------------------

_NO_INTERSECTION = 0
_POINT_INTERSECTION = 1
_COLLINEAR_INTERSECTION = 2


def _compute_intersection(p1: Point, p2: Point, q1: Point, q2: Point) -> tuple[int, Point]:
    """`RobustLineIntersector.computeIntersect`, returning `(result, intPt[0])`.

    Only `hasIntersection`, `getIntersectionNum` and `getIntersection(0)` are
    read by the curve generator, so the second intersection point of a collinear
    overlap is computed but not returned.
    """
    if not _envelopes_intersect(p1, p2, q1, q2):
        return _NO_INTERSECTION, p1
    pq1 = _orientation_index(p1, p2, q1)
    pq2 = _orientation_index(p1, p2, q2)
    if (pq1 > 0 and pq2 > 0) or (pq1 < 0 and pq2 < 0):
        return _NO_INTERSECTION, p1
    qp1 = _orientation_index(q1, q2, p1)
    qp2 = _orientation_index(q1, q2, p2)
    if (qp1 > 0 and qp2 > 0) or (qp1 < 0 and qp2 < 0):
        return _NO_INTERSECTION, p1
    if pq1 == 0 and pq2 == 0 and qp1 == 0 and qp2 == 0:
        return _collinear_intersection(p1, p2, q1, q2)
    if pq1 == 0 or pq2 == 0 or qp1 == 0 or qp2 == 0:
        # An endpoint is the intersection. JTS copies it rather than computing
        # it, so the value is exact.
        if p1 in (q1, q2):
            return _POINT_INTERSECTION, p1
        if p2 in (q1, q2):
            return _POINT_INTERSECTION, p2
        if pq1 == 0:
            return _POINT_INTERSECTION, q1
        if pq2 == 0:
            return _POINT_INTERSECTION, q2
        if qp1 == 0:
            return _POINT_INTERSECTION, p1
        return _POINT_INTERSECTION, p2
    return _POINT_INTERSECTION, _intersection(p1, p2, q1, q2)


def _collinear_intersection(p1: Point, p2: Point, q1: Point, q2: Point) -> tuple[int, Point]:
    p1q1p2 = _envelope_contains(p1, p2, q1)
    p1q2p2 = _envelope_contains(p1, p2, q2)
    q1p1q2 = _envelope_contains(q1, q2, p1)
    q1p2q2 = _envelope_contains(q1, q2, p2)
    if p1q1p2 and p1q2p2:
        return _COLLINEAR_INTERSECTION, q1
    if q1p1q2 and q1p2q2:
        return _COLLINEAR_INTERSECTION, p1
    if p1q1p2 and q1p1q2:
        point = q1 == p1 and not p1q2p2 and not q1p2q2
        return (_POINT_INTERSECTION if point else _COLLINEAR_INTERSECTION), q1
    if p1q1p2 and q1p2q2:
        point = q1 == p2 and not p1q2p2 and not q1p1q2
        return (_POINT_INTERSECTION if point else _COLLINEAR_INTERSECTION), q1
    if p1q2p2 and q1p1q2:
        point = q2 == p1 and not p1q1p2 and not q1p2q2
        return (_POINT_INTERSECTION if point else _COLLINEAR_INTERSECTION), q2
    if p1q2p2 and q1p2q2:
        point = q2 == p2 and not p1q1p2 and not q1p1q2
        return (_POINT_INTERSECTION if point else _COLLINEAR_INTERSECTION), q2
    return _NO_INTERSECTION, p1


def _intersection(p1: Point, p2: Point, q1: Point, q2: Point) -> Point:
    """`intersection`: normalise to the envelope centre, then homogeneous coordinates."""
    min_x = max(min(p1[0], p2[0]), min(q1[0], q2[0]))
    max_x = min(max(p1[0], p2[0]), max(q1[0], q2[0]))
    min_y = max(min(p1[1], p2[1]), min(q1[1], q2[1]))
    max_y = min(max(p1[1], p2[1]), max(q1[1], q2[1]))
    norm = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)
    n1 = (p1[0] - norm[0], p1[1] - norm[1])
    n2 = (p2[0] - norm[0], p2[1] - norm[1])
    n3 = (q1[0] - norm[0], q1[1] - norm[1])
    n4 = (q2[0] - norm[0], q2[1] - norm[1])

    px = n1[1] - n2[1]
    py = n2[0] - n1[0]
    pw = n1[0] * n2[1] - n2[0] * n1[1]
    qx = n3[1] - n4[1]
    qy = n4[0] - n3[0]
    qw = n3[0] * n4[1] - n4[0] * n3[1]
    x = py * qw - qy * pw
    y = qx * pw - px * qw
    w = px * qy - qx * py
    x_int = _div(x, w)
    y_int = _div(y, w)
    if not (math.isfinite(x_int) and math.isfinite(y_int)):
        # HCoordinate throws NotRepresentableException and JTS falls back.
        return _central_endpoint(p1, p2, q1, q2)
    int_pt = (x_int + norm[0], y_int + norm[1])
    if not (_envelope_contains(p1, p2, int_pt) and _envelope_contains(q1, q2, int_pt)):
        return _central_endpoint(p1, p2, q1, q2)
    return int_pt


def _central_endpoint(p1: Point, p2: Point, q1: Point, q2: Point) -> Point:
    """`CentralEndpointIntersector`: the input endpoint nearest their centroid."""
    centre = (
        (p1[0] + p2[0] + q1[0] + q2[0]) / 4.0,
        (p1[1] + p2[1] + q1[1] + q2[1]) / 4.0,
    )
    return min((p1, p2, q1, q2), key=lambda pt: _dist(pt, centre))


def _envelopes_intersect(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    """`Envelope.intersects(p1, p2, q1, q2)`."""
    for axis in (0, 1):
        if min(p1[axis], p2[axis]) > max(q1[axis], q2[axis]):
            return False
        if max(p1[axis], p2[axis]) < min(q1[axis], q2[axis]):
            return False
    return True


def _envelope_contains(p1: Point, p2: Point, q: Point) -> bool:
    """`Envelope.intersects(p1, p2, q)`, which is containment in the envelope."""
    return min(p1[0], p2[0]) <= q[0] <= max(p1[0], p2[0]) and min(p1[1], p2[1]) <= q[1] <= max(
        p1[1], p2[1]
    )


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------


def _orientation_index(p1: Point, p2: Point, q: Point) -> int:
    """`CGAlgorithms.orientationIndex`: +1 counter-clockwise, -1 clockwise, 0 collinear.

    JTS gets the exact sign from `RobustDeterminant.signOfDet2x2`. A float filter
    handles the common case and exact rationals settle the rest; both agree with
    the exact sign of the determinant of the input doubles, which is what
    `signOfDet2x2` is specified to return.
    """
    return _sign_of_det2x2(p2[0] - p1[0], p2[1] - p1[1], q[0] - p2[0], q[1] - p2[1])


def _sign_of_det2x2(x1: float, y1: float, x2: float, y2: float) -> int:
    """`RobustDeterminant.signOfDet2x2`: the exact sign of `x1*y2 - y1*x2`.

    Which deltas get handed to it is load-bearing and differs between callers,
    so the subtraction is deliberately left to them: `orientationIndex` takes
    differences between consecutive points, while `RayCrossingCounter` translates
    every point by the query point first. Those two disagree when a coordinate is
    small enough that one of the subtractions cancels away and the other does
    not, which is exactly the situation at a buffer boundary vertex.
    """
    a = x1 * y2
    b = y1 * x2
    det = a - b
    if not math.isfinite(det):
        return 0
    error = _ORIENTATION_FILTER * (abs(a) + abs(b))
    if det > error:
        return 1
    if det < -error:
        return -1
    exact = Fraction(x1) * Fraction(y2) - Fraction(y1) * Fraction(x2)
    if exact > 0:
        return 1
    if exact < 0:
        return -1
    return 0


def _distance_point_line(p: Point, a: Point, b: Point) -> float:
    """`CGAlgorithms.distancePointLine`, the non-robust one the simplifier uses."""
    if a == b:
        return _dist(p, a)
    len2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
    r = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / len2
    if r <= 0.0:
        return _dist(p, a)
    if r >= 1.0:
        return _dist(p, b)
    s = ((a[1] - p[1]) * (b[0] - a[0]) - (a[0] - p[0]) * (b[1] - a[1])) / len2
    return abs(s) * math.sqrt(len2)
