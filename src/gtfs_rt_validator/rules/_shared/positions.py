"""`Position` predicates and the two unit conversions, from `util/GtfsUtils.java`.

Reached by E026, E027, E028, E029 and W004.

```java
public static boolean isPositionValid(Position p) {          // :136-145
    if (p.getLatitude() < -90f || p.getLatitude() > 90f) return false;
    if (p.getLongitude() < -180f || p.getLongitude() > 180f) return false;
    return true;
}
public static boolean isBearingValid(Position p) {           // :152-160
    if (!p.hasBearing()) return true;
    return !(p.getBearing() < 0 || p.getBearing() > 360);
}
public static boolean isPositionWithinShape(Position v, Shape bounds) {  // :169-173
    ShapeFactory sf = GEO.getShapeFactory();
    Point p = sf.pointXY(v.getLongitude(), v.getLatitude());
    return bounds.relate(p).equals(SpatialRelation.CONTAINS);
}
public static float toMilesPerHour(float m) { return m * 2.23694f; }     // :74-76
public static double toMiles(double m) { return m * 0.000621371d; }      // :83-85
```

Three readings are load-bearing and none of them is what a fresh design would
choose. `isPositionValid` reads latitude and longitude with no `has` guard, so a
`Position` carrying neither is valid at (0, 0); E026 catches the missing pair
itself, one branch earlier. `isBearingValid` does have the guard and returns
true, so a vehicle reporting no bearing never trips E027. All the bounds are
inclusive, at -90, -180, 90, 180 and at both 0 and 360.

The geometry lives in `geometry/`, which reproduces spatial4j 0.6 and JTS 1.13
already; nothing here recomputes any of it. What this module owns is the point:
its float32 narrowing, its world-bounds check, and spatial4j's rule that a point
with a NaN longitude is *empty* and therefore disjoint from everything.

Stdlib and this project's own leaf modules only. Nothing from `runner/`, which
would drag the static adapter and the sibling package in behind it.
"""

from __future__ import annotations

import math
import struct
from typing import Protocol

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.rules._shared.javafmt import float32

__all__ = [
    "METERS_PER_SECOND_TO_MILES_PER_HOUR",
    "METERS_TO_MILES",
    "Bounds",
    "is_bearing_valid",
    "is_position_valid",
    "is_position_within_shape",
    "to_miles",
    "to_miles_per_hour",
]


class Bounds(Protocol):
    """What `isPositionWithinShape` calls a `Shape`: something a point is in or out of.

    `geometry.bbox.Rectangle` satisfies it as it stands, which is E028's
    bounding box. E029's buffered trip shape is a function rather than an object
    in `geometry.buffer`, so the rule that owns E029 supplies the small adapter;
    building one here would guess at an interface no caller has asked for yet.
    """

    def contains(self, lon: float, lat: float) -> bool: ...


#: `2.23694f`, which as a double is 2.2369399070739746 and not 2.23694.
METERS_PER_SECOND_TO_MILES_PER_HOUR = struct.unpack("<f", struct.pack("<f", 2.23694))[0]

#: `0.000621371d`, a plain double.
METERS_TO_MILES = 0.000621371

#: `SpatialContext.GEO`'s world bounds, which `pointXY` verifies against.
_MAX_LATITUDE = 90.0
_MAX_LONGITUDE = 180.0


def is_position_valid(position: Msg) -> bool:
    """Are latitude and longitude inside the world? Bounds inclusive.

    A NaN coordinate is valid, because every comparison against NaN is false in
    Java and in Python alike. A feed can carry one: the wire format has room for
    it and `isPositionValid` is what E026 tests, so a NaN position reaches E028
    rather than being reported.
    """
    latitude = _float32(position.get("latitude"))
    longitude = _float32(position.get("longitude"))
    if latitude < -_MAX_LATITUDE or latitude > _MAX_LATITUDE:
        return False
    return not (longitude < -_MAX_LONGITUDE or longitude > _MAX_LONGITUDE)


def is_bearing_valid(position: Msg) -> bool:
    """Is the bearing between 0 and 360 inclusive? **An absent bearing is valid.**"""
    if not position.has("bearing"):
        return True
    bearing = _float32(position.get("bearing"))
    return not (bearing < 0.0 or bearing > 360.0)


def is_position_within_shape(position: Msg, bounds: Bounds) -> bool:
    """Is the position inside `bounds`? `relate(point) == CONTAINS`, nothing weaker.

    Two spatial4j behaviours live here rather than in `geometry/`, because both
    belong to the point and not to the shape.

    A NaN longitude answers False whatever the shape is. `PointImpl.isEmpty()`
    is `Double.isNaN(x)` alone, and `RectangleImpl.relate(Shape)` short-circuits
    to DISJOINT for an empty argument. A NaN *latitude* does not: it reaches the
    normal comparisons, which are all false, so a point whose longitude is in
    range answers CONTAINS. Measured against spatial4j 0.6 on JDK 17, and pinned
    in `tests/test_shared_positions.py`.

    A coordinate outside the world raises `ValueError`, mirroring the
    `InvalidShapeException` that `pointXY` throws and that upstream catches
    nowhere. It cannot happen under compat: E028 and E029 both sit behind
    `is_position_valid`, which has already rejected exactly these values. It is
    reproduced anyway so that a future caller which forgets the gate fails
    loudly rather than quietly answering for a point Java would have refused to
    build.
    """
    longitude = _float32(position.get("longitude"))
    latitude = _float32(position.get("latitude"))
    _verify_point(longitude, latitude)
    if math.isnan(longitude):
        return False
    return bounds.contains(longitude, latitude)


def to_miles_per_hour(meters_per_second: float) -> float:
    """`m * 2.23694f` in float arithmetic, which is not the double product.

    Both operands are floats, so the exact product has at most 48 significant
    bits and lands in a double unrounded; narrowing that to a float is therefore
    the same single rounding the JVM does. W004 formats the result with
    `%.2f`, which is `javafmt`'s job: this returns a number.
    """
    narrowed = _float32(meters_per_second)
    return _float32(narrowed * METERS_PER_SECOND_TO_MILES_PER_HOUR)


def to_miles(meters: float) -> float:
    """`m * 0.000621371d` in double arithmetic. Plain Python, and no narrowing."""
    return meters * METERS_TO_MILES


def _verify_point(longitude: float, latitude: float) -> None:
    """`ShapeFactoryImpl.pointXY`'s `verifyX` and `verifyY`.

    NaN passes, as it does in Java: the check is a pair of comparisons, not a
    range test.
    """
    if longitude < -_MAX_LONGITUDE or longitude > _MAX_LONGITUDE:
        raise ValueError(
            f"Bad X value {longitude} is not in boundary "
            f"Rect(minX=-180.0,maxX=180.0,minY=-90.0,maxY=90.0)"
        )
    if latitude < -_MAX_LATITUDE or latitude > _MAX_LATITUDE:
        raise ValueError(
            f"Bad Y value {latitude} is not in boundary "
            f"Rect(minX=-180.0,maxX=180.0,minY=-90.0,maxY=90.0)"
        )


def _float32(value: object) -> float:
    """The double a Java `float` holding this value would widen to.

    A decoded `Position` already holds float32 values, so this is a no-op there.
    It is applied anyway because a hand-built `Msg`, which is how a test states
    an absent field, can hold a double, and a helper that answered differently
    for the two would be testable only through the encoder.

    The narrowing itself is `javafmt.float32` rather than a second `struct`
    round trip written out here. The two were written independently and agreed,
    which is exactly the situation the project rule against copy-pasted shared
    logic is about: they would not have stayed agreed. All this adds is
    accepting an `object` off a `Msg` and coercing it.
    """
    return float32(float(value))  # type: ignore[arg-type]
