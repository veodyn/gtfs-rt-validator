"""`GtfsUtils` position and unit helpers, pinned to upstream and to spatial4j.

Ported verbatim from `gtfs-realtime-validator-lib/src/test/.../UtilTest.java`:
`testValidPosition` (:450-495), `testValidBearing` (:497-521) and
`testPositionWithinShape` (:523-545). Those three fix every boundary: -90, -180,
90, 180 valid and -91, -181, 91, 181 invalid; bearing 0 and 360 valid, -1 and
361 invalid; and the USF Bull Runner bounding box containing the campus but not
downtown Tampa.

Upstream tests nothing else here, so the rest is ours. Three of those cases were
measured rather than reasoned, by running `SpatialContext.GEO.getShapeFactory()`
from `tools/.jars/spatial4j-0.6.jar` on JDK 17:

    box=Rect(minX=-82.438456,maxX=-82.399531,minY=28.041606,maxY=28.082202)
    pointXY(-181.0,0.0)  -> InvalidShapeException: Bad X value -181.0 is not in
                            boundary Rect(minX=-180.0,...,maxY=90.0)
    pointXY(NaN,0.0)     -> DISJOINT
    pointXY(-82.4139,NaN) -> CONTAINS

A NaN longitude is DISJOINT because `PointImpl.isEmpty()` is `isNaN(x)` alone
and `RectangleImpl.relate(Shape)` answers DISJOINT for an empty argument; a NaN
latitude with an in-range longitude short-circuits to CONTAINS before the
latitude is looked at twice. Both are reachable from a feed, because a proto
float field can carry NaN and `isPositionValid` passes it: every comparison
against NaN is false.

The unit conversions are measured too, from `26.0f * 2.23694f` and
`1609 * 0.000621371d` on the same JDK.
"""

from __future__ import annotations

import math
import struct

import pytest

from gtfs_rt_validator.geometry.bbox import Rectangle
from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.rules._shared.positions import (
    is_bearing_valid,
    is_position_valid,
    is_position_within_shape,
    to_miles,
    to_miles_per_hour,
)

#: The four corners `testPositionWithinShape` builds its bounding box from, in
#: upstream's own `pointXY(lon, lat)` order.
USF_CORNERS = (
    (-82.438456, 28.041606),
    (-82.438456, 28.082202),
    (-82.399531, 28.082202),
    (-82.399531, 28.041606),
)


def position(**fields: float) -> Msg:
    """A `Position` through the real encoder and decoder.

    Which matters for more than realism: `latitude`, `longitude` and `bearing`
    are proto floats, so the round trip is what rounds `28.0587` to the
    `28.058700561523438` a rule actually reads.
    """
    return decode(encode(fields, V2015, "Position"), V2015, "Position")


def as_float32(value: float) -> float:
    """The double a Java `float` holding this value would widen to."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def usf_bounding_box() -> Rectangle:
    """`sf.multiPoint()...build().getBoundingBox()` over the four USF corners."""
    return Rectangle.from_points(USF_CORNERS)


def test_valid_position() -> None:
    """UtilTest.testValidPosition, verbatim."""
    assert is_position_valid(position(latitude=0, longitude=0))
    assert is_position_valid(position(latitude=-90, longitude=-180))
    assert is_position_valid(position(latitude=90, longitude=180))
    assert not is_position_valid(position(latitude=-91, longitude=0))
    assert not is_position_valid(position(latitude=0, longitude=-181))
    assert not is_position_valid(position(latitude=91, longitude=0))
    assert not is_position_valid(position(latitude=0, longitude=181))


def test_valid_bearing() -> None:
    """UtilTest.testValidBearing, verbatim."""
    assert is_bearing_valid(position(latitude=0, longitude=0, bearing=0))
    assert is_bearing_valid(position(latitude=0, longitude=0, bearing=360))
    assert not is_bearing_valid(position(latitude=0, longitude=0, bearing=-1))
    assert not is_bearing_valid(position(latitude=0, longitude=0, bearing=361))


def test_an_absent_bearing_is_valid() -> None:
    """`isBearingValid` returns true before reading anything. Ours, not upstream's.

    E027 therefore never fires on a vehicle that reports no bearing, which is
    the difference between this helper and `isPositionValid` below.
    """
    assert is_bearing_valid(position(latitude=0, longitude=0))


def test_an_absent_latitude_reads_as_zero_and_is_valid() -> None:
    """No `has` guard in the Java, so the proto default answers. Ours.

    E026 catches the missing-lat/long case itself, before it ever calls this,
    which is why upstream can afford the unguarded read.
    """
    empty = Msg(V2015.message("Position"), V2015)
    assert is_position_valid(empty)
    assert is_bearing_valid(empty)


def test_a_nan_coordinate_is_a_valid_position() -> None:
    """Every comparison against NaN is false, in Java and in Python alike."""
    assert is_position_valid(position(latitude=math.nan, longitude=math.nan))


def test_position_within_shape() -> None:
    """UtilTest.testPositionWithinShape, verbatim, plus the measured box bounds."""
    box = usf_bounding_box()
    assert (box.min_x, box.max_x, box.min_y, box.max_y) == (
        -82.438456,
        -82.399531,
        28.041606,
        28.082202,
    )
    campus = position(latitude=28.0587, longitude=-82.4139)
    assert is_position_within_shape(campus, box)
    downtown = position(latitude=27.9482837, longitude=-82.4655826)
    assert not is_position_within_shape(downtown, box)


def test_the_shape_boundary_is_inclusive() -> None:
    """A corner of the box counts as inside, and the position has to reach it.

    Measured, not upstream's. Both halves are:

        box32=Rect(minX=-82.4384536743164,maxX=-82.39952850341797,
                   minY=28.041606903076172,maxY=28.082202911376953)
        pointXY(-82.39952850341797,28.082202911376953) vs box32 -> CONTAINS
        pointXY(-82.39952850341797,28.082202911376953) vs box   -> DISJOINT

    The second line is the trap. The box is built from `shapes.txt` or
    `stops.txt`, which onebusaway reads as doubles, while the position comes off
    the wire as a float. `-82.399531` narrows *up* to `-82.39952850341797`, past
    the box's own eastern edge, so a vehicle parked exactly on the easternmost
    stop is outside the unbuffered box. The buffer of a mile is what stops E028
    firing on it in practice, and it is why this test builds a second box out of
    the narrowed corners rather than asserting the corner of the first one.
    """
    box = usf_bounding_box()
    corner = position(latitude=28.082202, longitude=-82.399531)
    assert not is_position_within_shape(corner, box)

    narrowed = Rectangle.from_points(
        [(as_float32(lon), as_float32(lat)) for lon, lat in USF_CORNERS]
    )
    assert is_position_within_shape(corner, narrowed)
    assert is_position_within_shape(position(latitude=28.041606, longitude=-82.438456), narrowed)


def test_a_nan_longitude_is_disjoint_but_a_nan_latitude_is_not() -> None:
    """spatial4j's empty-point rule, measured. See the module docstring."""
    box = usf_bounding_box()
    assert not is_position_within_shape(position(latitude=28.0587, longitude=math.nan), box)
    assert is_position_within_shape(position(latitude=math.nan, longitude=-82.4139), box)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(0.0, -181.0), (91.0, 0.0), (0.0, math.inf), (-math.inf, 0.0)],
)
def test_a_point_outside_the_world_raises(latitude: float, longitude: float) -> None:
    """`pointXY` verifies against the world bounds before the box is consulted.

    Measured: spatial4j throws `InvalidShapeException`, which upstream catches
    nowhere. It is unreachable from E028 and E029, which both sit behind
    `isPositionValid`, so this pins a contract rather than a compat behaviour.
    """
    with pytest.raises(ValueError):
        is_position_within_shape(
            position(latitude=latitude, longitude=longitude), usf_bounding_box()
        )


def test_to_miles_per_hour_is_float_arithmetic() -> None:
    """`26.0f * 2.23694f` is `58.16044` in Java, and the double product is not.

    26.0 m/s is `MAX_REALISTIC_SPEED_METERS_PER_SECOND`, so this is the exact
    product W004 formats.
    """
    assert to_miles_per_hour(26.0) == as_float32(58.16044)
    assert to_miles_per_hour(0.1) == as_float32(0.223694)
    assert to_miles_per_hour(-1.5) == as_float32(-3.3554099)
    assert to_miles_per_hour(27.5) == as_float32(61.515846)
    assert to_miles_per_hour(26.0) != 26.0 * 2.23694


def test_to_miles_is_double_arithmetic() -> None:
    """The two distances E028 and E029 name in their occurrence text."""
    assert to_miles(1609) == 0.999785939
    assert to_miles(200) == 0.1242742


def test_the_conversions_return_numbers_rather_than_text() -> None:
    """Formatting is `javafmt`'s job, so a caller can round once, at the end."""
    assert isinstance(to_miles_per_hour(1.0), float)
    assert isinstance(to_miles(1.0), float)
