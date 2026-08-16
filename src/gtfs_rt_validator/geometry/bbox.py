"""spatial4j 0.6's geodetic rectangle, reproduced in stdlib Python.

E028 asks whether a vehicle position falls inside a bounding box built over
every stop, or over every shape point, and grown by a mile. Upstream builds that
box with `JtsSpatialContext.GEO.getShapeFactory().multiPoint()`, takes
`getBoundingBox()`, and calls `RectangleImpl.getBuffered`. This module is that
path, and only that path: it decides no rules and formats no messages.

Three things here are not what a first guess would write, and each is measured
against the jar by `tests/test_bbox.py`:

1. **The buffer is asymmetric.** Latitude grows by `distance`. Longitude grows
   by `asin(sin(distRad) / cos(latRad))`, evaluated at whichever of the box's
   two latitudes is nearer a pole, so it is larger everywhere off the equator
   and much larger near a pole. At 28 N a 1609 m buffer is 0.01447 degrees of
   latitude and 0.01640 degrees of longitude.
2. **The multipoint bounding box is not `min(lons)` to `max(lons)`.** When the
   points span more than 180 degrees, spatial4j finds the widest empty gap in
   longitude and returns the complement, which is how a feed either side of the
   antimeridian gets a narrow box that crosses it rather than one wrapping the
   planet.
3. **A box over no points is all-NaN and is DISJOINT from everything.** It does
   not raise, and `contains` answers False for every point, so E028 fires for
   every vehicle position. That is upstream's behaviour, measured, and it is
   what a feed whose stops all lack coordinates actually produces.

Sources, all at spatial4j 0.6:
`shape/impl/RectangleImpl.java` (`getBuffered`, `relate`, `getWidth`),
`distance/DistanceUtils.java` (`calcBoxByDistFromPt_deltaLonDEG`, `normLonDEG`),
`shape/jts/JtsGeometry.java` (`computeGeoBBox`),
`shape/impl/BBoxCalculator.java` (the widest-gap search), and
`shape/impl/ShapeFactoryImpl.java` (`rect`). Upstream's own call sites are
`GtfsMetadata.java:122-140, 219-233` and `GtfsUtils.java:169-173`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

# DistanceUtils, lines 51-67. The radius is the IUGG mean, not 6371.0 and not the
# equatorial 6378.137; a different one moves the buffer in the seventh decimal
# place of degrees, which is enough to flip a point that sits on the boundary.
EARTH_MEAN_RADIUS_KM = 6371.0087714
DEGREES_TO_RADIANS = math.pi / 180
RADIANS_TO_DEGREES = 1 / DEGREES_TO_RADIANS
DEG_TO_KM = DEGREES_TO_RADIANS * EARTH_MEAN_RADIUS_KM
KM_TO_DEG = 1 / DEG_TO_KM

# GtfsMetadata.java:43 and :122. Roughly a mile, and the only buffer this module
# is used with; the 200 m trip buffer belongs to the JTS polyline buffer instead.
REGION_BUFFER_METERS = 1609
REGION_BUFFER_DEGREES = KM_TO_DEG * (REGION_BUFFER_METERS / 1000.0)

#: `GtfsMetadata.TRIP_BUFFER_METERS`, the distance E029 allows a vehicle to sit
#: from its trip's shape, and the number its occurrence text renders as `200.0`.
#:
#: Here rather than in `buffer.py`, which is where the buffering that consumes it
#: lives, for two reasons. It sits beside `KM_TO_DEG` and the region buffer, so
#: the two distances upstream declares are declared together. And `buffer.py` is
#: held to stdlib-only imports by `tests/test_buffer.py`, which allows a module
#: of its own three-file split and nothing else, so putting it there would have
#: meant either a cross-import that test forbids or widening the test.
#:
#: It must live in `geometry/` rather than in `static/`, because both consumers
#: need it and only one of them may import the other: `static/context.py` buffers
#: trip shapes with it, `rules/_shared/vehicle_bounds.py` renders it into E029's
#: prefix, and the rules layer may not reach `static/`, which
#: `tests/test_only_adapter_touches_the_sibling.py` enforces. Declared in both
#: places instead was the alternative, and a constant written twice becomes two
#: constants.
TRIP_BUFFER_METERS = 200
TRIP_BUFFER_DEGREES = KM_TO_DEG * (TRIP_BUFFER_METERS / 1000.0)


def norm_lon_deg(lon_deg: float) -> float:
    """`DistanceUtils.normLonDEG`: fold a longitude into -180 to +180.

    The in-range short-circuit is spatial4j's and is load-bearing rather than an
    optimisation: `(lon + 180) % 360 - 180` shifts the last bits of an
    already-valid longitude, and the buffered box's bounds are compared exactly.
    Java's `%` on doubles is truncated, which is `math.fmod`, not `%`.
    """
    if -180 <= lon_deg <= 180:
        return lon_deg
    off = math.fmod(lon_deg + 180, 360)
    if off < 0:
        return 180 + off
    if off == 0 and lon_deg > 0:
        return 180
    return -180 + off


def delta_lon_deg(lat: float, dist_deg: float) -> float:
    """`DistanceUtils.calcBoxByDistFromPt_deltaLonDEG`, minus its unused `lon`.

    Half the width of the bounding box of a circle of radius `dist_deg` centred
    at latitude `lat`: `asin(sin(distRad) / cos(latRad))`, in degrees.

    Java's `Math.asin` answers NaN outside [-1, 1] and spatial4j turns that into
    90; Python's raises `ValueError`, so the domain is checked first. The same
    branch catches a NaN latitude, which is how the empty box gets a longitude
    delta of 90 on its way to staying empty.
    """
    if dist_deg == 0:
        return 0.0
    lat_rad = lat * DEGREES_TO_RADIANS
    dist_rad = dist_deg * DEGREES_TO_RADIANS
    ratio = math.sin(dist_rad) / math.cos(lat_rad)
    if -1.0 <= ratio <= 1.0:
        return math.asin(ratio) * RADIANS_TO_DEGREES
    return 90.0


def _widest_gap_lon_range(lons: Iterable[float]) -> tuple[float, float]:
    """`BBoxCalculator`, specialised to points.

    The general algorithm keeps a sorted set of disjoint longitude ranges and
    merges each new one in. Every range here is a single point, `[x, x]`, and
    for those `expandXRange` reduces to inserting `x` into a sorted set of
    distinct longitudes: the "entry contains maxX" branch fires only when the
    entry *is* `x`, in which case there is nothing to do, and the world-wrap
    branch that sets -180/+180 sits inside it and is therefore unreachable.
    `processRanges` below is then transcribed as it stands.

    It answers the complement of the widest empty gap, so points at 179.9 and
    -179.9 give `(179.9, -179.9)`, a box that crosses the dateline, rather than
    one spanning almost the whole planet.
    """
    ordered = sorted(set(lons))
    if len(ordered) == 1:
        return ordered[0], ordered[0]
    # Java seeds these to +/- infinity and only assigns inside the `gap >
    # biggestGap` branch. With two or more distinct longitudes the gaps sum to
    # 360, so at least one is positive and the branch always fires.
    min_x = math.inf
    max_x = -math.inf
    prev = ordered[-1]
    biggest_gap = 0.0
    possible_remaining_gap = 360.0
    for x in ordered:
        # For point ranges the range width is zero, so these two are equal.
        # Both are kept so the transcription lines up with the original.
        width_plus_gap = x - prev
        if width_plus_gap < 0:
            width_plus_gap += 360
        gap = x - prev
        if gap < 0:
            gap += 360
        possible_remaining_gap -= width_plus_gap
        if gap > biggest_gap:
            biggest_gap = gap
            min_x = x
            max_x = prev
            if possible_remaining_gap <= biggest_gap:
                break
        prev = x
    return min_x, max_x


@dataclass(frozen=True, slots=True)
class Rectangle:
    """A geodetic bounding box in lon/lat degrees.

    `min_x` greater than `max_x` means the box crosses the antimeridian, which
    spatial4j represents the same way. All four bounds NaN means empty.

    Dataclass equality compares the four floats, so an empty rectangle is not
    equal to itself. Compare with `is_empty`, not with `==`.
    """

    min_x: float
    max_x: float
    min_y: float
    max_y: float

    @classmethod
    def from_points(cls, points: Iterable[tuple[float, float]]) -> Rectangle:
        """`sf.multiPoint()...build().getBoundingBox()`, as `GtfsMetadata` builds it.

        `points` are `(lon, lat)` pairs, matching spatial4j's `pointXY` order.
        Reproduces `JtsGeometry.computeGeoBBox`: the plain envelope, except that
        a set of more than one point spanning more than 180 degrees of longitude
        goes through the widest-gap search instead.
        """
        pairs = list(points)
        if not pairs:
            # JtsGeometry's constructor: an empty geometry gets Rect(NaN x4).
            return cls(math.nan, math.nan, math.nan, math.nan)
        lons = [lon for lon, _ in pairs]
        lats = [lat for _, lat in pairs]
        min_x, max_x = min(lons), max(lons)
        # `env.getWidth() > 180 && geoms.getNumGeometries() > 1`. The count is of
        # points as given, duplicates included, which is what createMultiPoint
        # produces.
        if max_x - min_x > 180 and len(pairs) > 1:
            min_x, max_x = _widest_gap_lon_range(lons)
        return cls(min_x, max_x, min(lats), max(lats))

    @property
    def is_empty(self) -> bool:
        """`RectangleImpl.isEmpty`: NaN in `min_x` is the whole test."""
        return math.isnan(self.min_x)

    @property
    def crosses_dateline(self) -> bool:
        return self.min_x > self.max_x

    @property
    def width(self) -> float:
        """`RectangleImpl.getWidth`, which adds 360 for a dateline-crossing box."""
        w = self.max_x - self.min_x
        if w < 0:
            w += 360
        return w

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def buffered(self, distance_degrees: float) -> Rectangle:
        """`RectangleImpl.getBuffered` in the geo branch, all four cases.

        Touching either pole widens the box to the whole world in longitude,
        because past a pole every meridian is in range. Otherwise latitude grows
        by `distance_degrees` and longitude by `delta_lon_deg` evaluated at the
        latitude nearer a pole, which can still be wide enough to wrap the world
        on its own.
        """
        d = distance_degrees
        if self.max_y + d >= 90:
            return _make_rectangle(-180.0, 180.0, max(-90.0, self.min_y - d), 90.0)
        if self.min_y - d <= -90:
            return _make_rectangle(-180.0, 180.0, -90.0, min(90.0, self.max_y + d))
        closest_to_pole_y = self.max_y if abs(self.max_y) > abs(self.min_y) else self.min_y
        lon_distance = delta_lon_deg(closest_to_pole_y, d)
        if lon_distance * 2 + self.width >= 360:
            return _make_rectangle(-180.0, 180.0, self.min_y - d, self.max_y + d)
        return _make_rectangle(
            norm_lon_deg(self.min_x - lon_distance),
            norm_lon_deg(self.max_x + lon_distance),
            self.min_y - d,
            self.max_y + d,
        )

    def contains(self, lon: float, lat: float) -> bool:
        """`GtfsUtils.isPositionWithinShape`: `relate(point) == CONTAINS`.

        A rectangle answers only CONTAINS or DISJOINT, and the boundary counts
        as CONTAINS, so this is inclusive on all four edges.

        It never raises. The empty-box guard comes from `relate(Shape)`, which
        upstream reaches because it holds the box as a `Shape`; taking the
        `relate(Point)` overload directly would skip it and let NaN comparisons
        answer for themselves. Upstream's own `pointXY` would reject a longitude
        outside +/-180 or a latitude outside +/-90 with an `InvalidShapeException`
        before ever getting here. That check belongs to whichever rule builds
        the point, not to the box, and it is deliberately not made here: a
        malformed feed is data, not an exception.
        """
        if self.is_empty:
            return False
        if lat > self.max_y or lat < self.min_y:
            return False
        min_x = self.min_x
        max_x = self.max_x
        p_x = lon
        # Unwrap a dateline-crossing box so max_x sits past +180, then shift the
        # point by a whole turn if that is what brings it into range.
        raw_width = max_x - min_x
        if raw_width < 0:
            max_x = min_x + (raw_width + 360)
        if p_x < min_x:
            p_x += 360
        elif p_x > max_x:
            p_x -= 360
        else:
            return True
        return not (p_x < min_x or p_x > max_x)


def _make_rectangle(min_x: float, max_x: float, min_y: float, max_y: float) -> Rectangle:
    """`ShapeFactoryImpl.rect` in the geo branch, reduced to what can fire here.

    Its only effect on a value is the dateline-edge nudge below: an edge exactly
    on +/-180 is moved to the other sign so a rectangle with real width is not
    read as crossing the dateline. Its four validity checks (latitudes inside
    +/-90, `min_y <= max_y`, longitudes inside +/-180) cannot fail on anything
    `buffered` produces: the pole branches clamp, the middle branch is guarded
    by those same pole tests, and `norm_lon_deg` bounds the longitudes. NaN
    passes every one of them, which is how the empty box survives buffering.
    """
    if min_x == 180 and min_x != max_x:
        min_x = -180.0
    elif max_x == -180 and min_x != max_x:
        max_x = 180.0
    return Rectangle(min_x, max_x, min_y, max_y)
