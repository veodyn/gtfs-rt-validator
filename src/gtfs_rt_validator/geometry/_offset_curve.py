"""`BufferInputLineSimplifier` and `OffsetSegmentGenerator`, ported from JTS 1.13.

Split out of `buffer.py`, which holds the module docstring for the reproduction
as a whole and drives both of these from `OffsetCurveBuilder.getLineCurve`. The
`BufferParameters` constants sit here, next to the code that reads them;
`buffer.py` re-exports them because callers and tests import them from there.

Stdlib only, by this project's no-third-party-runtime rule, enforced for this
module too by
`tests/test_buffer.py::test_buffer_imports_only_the_standard_library`.
"""

from __future__ import annotations

import math

from gtfs_rt_validator.geometry._predicates import (
    _CLOCKWISE,
    _COLLINEAR_INTERSECTION,
    _COUNTERCLOCKWISE,
    _NO_INTERSECTION,
    Point,
    _compute_intersection,
    _dist,
    _distance_point_line,
    _offset_segment,
    _orientation_index,
)

# BufferParameters defaults, printed by `DumpJtsBuffer --params` rather than read
# off the documentation: quadrantSegments 8, endCapStyle CAP_ROUND (1), joinStyle
# JOIN_ROUND (1), mitreLimit 5.0, isSingleSided false. Only the round styles are
# reachable here, so mitre and bevel joins are deliberately not ported.
QUADRANT_SEGMENTS = 8
FILLET_ANGLE_QUANTUM = math.pi / 2.0 / QUADRANT_SEGMENTS

# OffsetCurveBuilder.SIMPLIFY_FACTOR. In 1.13 this is private to the curve
# builder, not a BufferParameters field; it moved there in later versions.
SIMPLIFY_FACTOR = 100.0

# OffsetSegmentGenerator's snapping and closing-segment heuristics.
CURVE_VERTEX_SNAP_DISTANCE_FACTOR = 1.0e-6
OFFSET_SEGMENT_SEPARATION_FACTOR = 1.0e-3
INSIDE_TURN_VERTEX_SNAP_DISTANCE_FACTOR = 1.0e-3
# 1 rather than 80 whenever quadrantSegments < 8 or the join style is not round,
# neither of which happens with the defaults above.
CLOSING_SEG_LENGTH_FACTOR = 80


# ---------------------------------------------------------------------------
# BufferInputLineSimplifier
# ---------------------------------------------------------------------------


def _simplify(line: list[Point], distance_tol: float) -> list[Point]:
    """`BufferInputLineSimplifier.simplify`.

    A positive tolerance simplifies concavities on the left, a negative one on
    the right. End segments are never simplified, so the caps stay faithful.
    """
    tol = abs(distance_tol)
    angle_orientation = _CLOCKWISE if distance_tol < 0 else _COUNTERCLOCKWISE
    deleted = [False] * len(line)

    while _delete_shallow_concavities(line, tol, angle_orientation, deleted):
        pass
    return [p for i, p in enumerate(line) if not deleted[i]]


def _delete_shallow_concavities(
    line: list[Point], tol: float, angle_orientation: int, deleted: list[bool]
) -> bool:
    index = 1
    mid = _next_kept(line, deleted, index)
    last = _next_kept(line, deleted, mid)
    changed = False
    while last < len(line):
        if _is_deletable(line, index, mid, last, tol, angle_orientation):
            deleted[mid] = True
            changed = True
            index = last
        else:
            index = mid
        mid = _next_kept(line, deleted, index)
        last = _next_kept(line, deleted, mid)
    return changed


def _next_kept(line: list[Point], deleted: list[bool], index: int) -> int:
    nxt = index + 1
    while nxt < len(line) and deleted[nxt]:
        nxt += 1
    return nxt


def _is_deletable(
    line: list[Point], i0: int, i1: int, i2: int, tol: float, angle_orientation: int
) -> bool:
    p0, p1, p2 = line[i0], line[i1], line[i2]
    if _orientation_index(p0, p1, p2) != angle_orientation:
        return False
    if not _distance_point_line(p1, p0, p2) < tol:
        return False
    # isShallowSampled is meant to check the sampled points against the p0-p2
    # chord, but isDeletable passes p1 into the parameter its signature names p2,
    # so what it actually measures is the deviation of the middle vertex from the
    # line p0 to inputLine[i]. The first sample is i0, where that line degenerates
    # to the point p0 and the "distance" becomes the whole length of p0-p1. So the
    # test passes only when the segment is itself shorter than the tolerance, and
    # a shallow concave vertex on an ordinary shape is kept rather than deleted.
    # Measured against the jar: the 24-point wiggle in the differential corpus has
    # a vertex 0.54 of a tolerance off the chord, and JTS keeps it. Reproduced bug
    # and all, because "fixing" it deletes vertices the jar keeps and moves the
    # buffer boundary by up to distance/100.
    inc = max((i2 - i0) // 10, 1)
    return all(_distance_point_line(p1, p0, line[i]) < tol for i in range(i0, i2, inc))


# ---------------------------------------------------------------------------
# OffsetSegmentGenerator, always with side == Position.LEFT
# ---------------------------------------------------------------------------


class _SegmentGenerator:
    """`OffsetSegmentGenerator` restricted to round joins and round caps.

    `computeLineBufferCurve` only ever offsets to the LEFT (it walks the line
    backwards for the right-hand side), so `side` is not a field here.
    """

    def __init__(self, distance: float) -> None:
        self.distance = distance
        self.min_vertex_distance = distance * CURVE_VERTEX_SNAP_DISTANCE_FACTOR
        self.coordinates: list[Point] = []
        self.s0: Point = (0.0, 0.0)
        self.s1: Point = (0.0, 0.0)
        self.s2: Point = (0.0, 0.0)
        self.offset0: tuple[Point, Point] = ((0.0, 0.0), (0.0, 0.0))
        self.offset1: tuple[Point, Point] = ((0.0, 0.0), (0.0, 0.0))

    # -- OffsetSegmentString ------------------------------------------------

    def add_pt(self, pt: Point) -> None:
        """Drops a vertex within `distance * 1e-6` of the previous one.

        The precision model is FLOATING, so `makePrecise` is a no-op and the
        coordinate is stored as computed.
        """
        if self.coordinates and _dist(pt, self.coordinates[-1]) < self.min_vertex_distance:
            return
        self.coordinates.append(pt)

    def close_ring(self) -> None:
        if not self.coordinates:
            return
        if self.coordinates[0] != self.coordinates[-1]:
            self.coordinates.append(self.coordinates[0])

    # -- curve construction -------------------------------------------------

    def init_side_segments(self, s1: Point, s2: Point) -> None:
        self.s1 = s1
        self.s2 = s2
        self.offset1 = _offset_segment(s1, s2, 1, self.distance)

    def add_first_segment(self) -> None:
        self.add_pt(self.offset1[0])

    def add_last_segment(self) -> None:
        self.add_pt(self.offset1[1])

    def add_next_segment(self, p: Point) -> None:
        self.s0, self.s1, self.s2 = self.s1, self.s2, p
        self.offset0 = _offset_segment(self.s0, self.s1, 1, self.distance)
        self.offset1 = _offset_segment(self.s1, self.s2, 1, self.distance)

        if self.s1 == self.s2:
            return

        orientation = _orientation_index(self.s0, self.s1, self.s2)
        if orientation == 0:
            self._add_collinear()
        elif orientation == _CLOCKWISE:  # outside turn, since side is always LEFT
            self._add_outside_turn(orientation)
        else:
            self._add_inside_turn()

    def _add_collinear(self) -> None:
        result, _ = _compute_intersection(self.s0, self.s1, self.s1, self.s2)
        # numInt < 2 means parallel and in the same direction, so the vertex can
        # be ignored: the offset lines are parallel too. numInt == 2 means the
        # line reverses onto itself and needs a full fillet around the turn.
        if result == _COLLINEAR_INTERSECTION:
            self._add_fillet_between(self.s1, self.offset0[1], self.offset1[0], _CLOCKWISE)

    def _add_outside_turn(self, orientation: int) -> None:
        # Nearly parallel segments make the join unstable to compute, so JTS
        # collapses the corner onto one offset endpoint.
        if (
            _dist(self.offset0[1], self.offset1[0])
            < self.distance * OFFSET_SEGMENT_SEPARATION_FACTOR
        ):
            self.add_pt(self.offset0[1])
            return
        self.add_pt(self.offset0[1])
        self._add_fillet_between(self.s1, self.offset0[1], self.offset1[0], orientation)
        self.add_pt(self.offset1[0])

    def _add_inside_turn(self) -> None:
        result, int_pt = _compute_intersection(
            self.offset0[0], self.offset0[1], self.offset1[0], self.offset1[1]
        )
        if result != _NO_INTERSECTION:
            self.add_pt(int_pt)
            return
        # The offsets do not reach each other: the corner is narrow relative to
        # the buffer distance. A closing segment keeps the curve continuous; it
        # ends up interior to the buffer polygon and so never shows in the
        # outline, but it does change how the curve nodes.
        if _dist(self.offset0[1], self.offset1[0]) < (
            self.distance * INSIDE_TURN_VERTEX_SNAP_DISTANCE_FACTOR
        ):
            self.add_pt(self.offset0[1])
            return
        self.add_pt(self.offset0[1])
        k = CLOSING_SEG_LENGTH_FACTOR
        self.add_pt(
            (
                (k * self.offset0[1][0] + self.s1[0]) / (k + 1),
                (k * self.offset0[1][1] + self.s1[1]) / (k + 1),
            )
        )
        self.add_pt(
            (
                (k * self.offset1[0][0] + self.s1[0]) / (k + 1),
                (k * self.offset1[0][1] + self.s1[1]) / (k + 1),
            )
        )
        self.add_pt(self.offset1[0])

    def add_line_end_cap(self, p0: Point, p1: Point) -> None:
        """`addLineEndCap`, CAP_ROUND branch: a half circle around `p1`."""
        offset_l = _offset_segment(p0, p1, 1, self.distance)
        offset_r = _offset_segment(p0, p1, -1, self.distance)
        angle = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        self.add_pt(offset_l[1])
        self._add_fillet(p1, angle + math.pi / 2, angle - math.pi / 2, _CLOCKWISE, self.distance)
        self.add_pt(offset_r[1])

    def create_circle(self, p: Point) -> None:
        """`createCircle`, for a shape that collapsed to a single point."""
        self.add_pt((p[0] + self.distance, p[1]))
        self._add_fillet(p, 0.0, 2.0 * math.pi, _CLOCKWISE, self.distance)
        self.close_ring()

    def _add_fillet_between(self, p: Point, p0: Point, p1: Point, direction: int) -> None:
        start_angle = math.atan2(p0[1] - p[1], p0[0] - p[0])
        end_angle = math.atan2(p1[1] - p[1], p1[0] - p[0])
        if direction == _CLOCKWISE:
            if start_angle <= end_angle:
                start_angle += 2.0 * math.pi
        elif start_angle >= end_angle:
            start_angle -= 2.0 * math.pi
        self.add_pt(p0)
        self._add_fillet(p, start_angle, end_angle, direction, self.distance)
        self.add_pt(p1)

    def _add_fillet(
        self, p: Point, start_angle: float, end_angle: float, direction: int, radius: float
    ) -> None:
        """The chord approximation itself: `nSegs` equal steps, endpoints excluded.

        `nSegs` rounds the swept angle to whole quanta, so a 90 degree turn gets
        8 chords and a shallower one proportionally fewer. This is where the
        polygon falls inside the true arc.
        """
        direction_factor = -1 if direction == _CLOCKWISE else 1
        total_angle = abs(start_angle - end_angle)
        n_segs = int(total_angle / FILLET_ANGLE_QUANTUM + 0.5)
        if n_segs < 1:
            return
        angle_inc = total_angle / n_segs
        curr = 0.0
        while curr < total_angle:
            angle = start_angle + direction_factor * curr
            self.add_pt((p[0] + radius * math.cos(angle), p[1] + radius * math.sin(angle)))
            curr += angle_inc
