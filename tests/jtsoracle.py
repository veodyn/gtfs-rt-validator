"""The jar's own answers, and the probe geometry they were measured at.

Split out of `tests/test_buffer.py`, which asserts against everything here and
says where it all came from. A module of plain data and helpers rather than
fixtures, following `tests/gtfsfixtures.py`: the corpus is read by
parametrisation at import time, which a fixture cannot serve.

The probes are rings of points at radii either side of `cos(pi/32) * distance`,
because that is the annulus where JTS's chord approximation of a round join or
cap falls inside the true offset. A distance-to-polyline test gets 54 of the 420
ring probes below wrong, which is what `test_a_distance_test_would_disagree`
holds on to.
"""

from __future__ import annotations

import itertools
import math

from gtfs_rt_validator.geometry import _predicates as predicates_module

# GtfsMetadata.TRIP_BUFFER_DEGREES: 200 m at the equator, in degrees.
TRIP_BUFFER_DEGREES = 0.001798640735523327
COS_HALF_QUANTUM = math.cos(math.pi / 32)
RADIUS_FRACTIONS = (
    0.9,
    COS_HALF_QUANTUM - 0.002,
    COS_HALF_QUANTUM,
    (COS_HALF_QUANTUM + 1) / 2,
    0.999,
    1.001,
)

SHALLOW_VERTEX = (-76.995, 28.0 + 0.9 * TRIP_BUFFER_DEGREES / 100)

# shape, the point the probe ring is centred on, and how many angles it uses.
SHAPES: dict[str, tuple[list[tuple[float, float]], tuple[float, float], int]] = {
    "straight28": ([(-77.0, 28.0), (-76.98, 28.0)], (-77.0, 28.0), 8),
    "straight50": ([(-77.0, 50.0), (-76.98, 50.0)], (-77.0, 50.0), 8),
    "corner": ([(-77.0, 28.0), (-76.99, 28.0), (-76.99, 28.01)], (-76.99, 28.0), 12),
    "shallow": ([(-77.0, 28.0), SHALLOW_VERTEX, (-76.99, 28.0)], SHALLOW_VERTEX, 8),
    "cross": (
        [(-77.0, 28.0), (-76.99, 28.01), (-77.0, 28.01), (-76.99, 28.0)],
        (-76.995, 28.005),
        8,
    ),
    "spike": ([(-77.0, 28.0), (-76.9999, 28.004), (-76.99978, 28.0)], (-76.9999, 28.004), 8),
    "dupes": ([(-77.0, 28.0), (-77.0, 28.0), (-76.99, 28.0), (-76.99, 28.0)], (-76.99, 28.0), 6),
    "identical": ([(-77.0, 28.0)] * 5, (-77.0, 28.0), 6),
    "twoidentical": ([(-77.0, 28.0), (-77.0, 28.0)], (-77.0, 28.0), 6),
}

# One character per probe, angle-major then radius, 1 for CONTAINS. Straight from
# the jar. The repeating "111000" is the annulus: the three radii at and below
# cos(pi/32) are inside and the three above are not, even though all six are
# within the buffer distance of the shape.
ORACLE = {
    "straight28": "111111111111111000111000111000111000111111111111",
    "straight50": "111111111111111000111000111000111000111111111111",
    "corner": ("111111111111111111111111111111111111111111111111111111111000111000111100"),
    "shallow": "111111111111111111111111111111111111111111111111",
    "cross": "111111111111111111111111111111111111111111111111",
    "spike": "111000111000111000111000111111111111111111111111",
    "dupes": "111000111100111111111111111111111000",
    "identical": "111000111100111000111000111100111000",
    "twoidentical": "111000111100111000111000111100111000",
}


def probes(key: str) -> list[tuple[float, float]]:
    _shape, (cx, cy), n_angles = SHAPES[key]
    points = []
    for i in range(n_angles):
        angle = 2 * math.pi * i / n_angles + 0.3
        for fraction in RADIUS_FRACTIONS:
            r = fraction * TRIP_BUFFER_DEGREES
            points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points


def naive_distance(shape: list[tuple[float, float]], lon: float, lat: float) -> float:
    """The shortcut this module exists to refuse: planar distance to the polyline."""
    pts = [p for i, p in enumerate(shape) if i == 0 or p != shape[i - 1]]
    if len(pts) == 1:
        return math.dist(pts[0], (lon, lat))
    return min(
        predicates_module._distance_point_line((lon, lat), a, b) for a, b in itertools.pairwise(pts)
    )


SHALLOW_RADII = (0.998, 1.0, 1.002, 1.004, 1.006, 1.008, 1.010, 1.012)


def shallow_probes() -> list[tuple[float, float]]:
    """Straight down from the shallow vertex, onto its concave side."""
    return [(SHALLOW_VERTEX[0], SHALLOW_VERTEX[1] - f * TRIP_BUFFER_DEGREES) for f in SHALLOW_RADII]


def wiggle() -> list[tuple[float, float]]:
    return [
        (-77.0 + 0.001 * i, 28.0 + 0.0004 * math.sin(i * 1.1) + 0.00002 * math.cos(i * 5.0))
        for i in range(24)
    ]


# spatial4j 0.6's EARTH_MEAN_RADIUS_KM, in metres, so the numbers below are the
# ones the rest of the validator's distances are expressed in.
METRES_PER_DEGREE = 6371008.7714 * math.pi / 180
