"""Java geometry, reproduced in stdlib Python, with a Java oracle beside each.

Two primitives, one per rule:

- `bbox` is spatial4j 0.6's `RectangleImpl`, which E028 uses to ask whether a
  vehicle position falls inside a bounding box over the feed's stops or shape
  points, grown by a mile. Oracle: `tools/DumpSpatial4jBoxes.java`.
- `buffer` is JTS 1.13's planar polyline buffer, which E029 uses to ask whether
  a vehicle position falls within 200 m of its trip's shape.

Neither knows what a rule is. Both are measured against the jar that defines
them rather than reasoned about, because both have behaviour that looks like a
bug and is not: the rectangle buffer is asymmetric between latitude and
longitude, and the polyline buffer is planar on raw degrees, so it is 200 m
north-south and `200 * cos(latitude)` m east-west. Under `--compat` that is the
point.

Only `bbox` is re-exported here. `buffer`'s surface lands with its own task.
"""

from __future__ import annotations

from gtfs_rt_validator.geometry.bbox import (
    EARTH_MEAN_RADIUS_KM,
    KM_TO_DEG,
    REGION_BUFFER_DEGREES,
    REGION_BUFFER_METERS,
    Rectangle,
)

__all__ = [
    "EARTH_MEAN_RADIUS_KM",
    "KM_TO_DEG",
    "REGION_BUFFER_DEGREES",
    "REGION_BUFFER_METERS",
    "Rectangle",
]
