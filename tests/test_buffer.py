"""`geometry/buffer.py` against answers taken from com.vividsolutions:jts:1.13.

Every expectation here was printed by the jar through `tools/DumpJtsBuffer.java`
and pasted in; none of it was worked out by hand. Regenerate with
`.venv/bin/python tools/diff_geometry_against_java.py`, which runs the same
families over a much larger corpus and needs the jar. This file needs no jar and
no JDK, so it pins what was measured rather than re-measuring it.

The shapes, the probe rings and the jar's answer for every probe live in
`tests/jtsoracle.py`; this module is the assertions written against them.
"""

from __future__ import annotations

import ast
import math
import sys
from pathlib import Path

import pytest

from gtfs_rt_validator.geometry import _offset_curve as offset_curve_module
from gtfs_rt_validator.geometry import _predicates as predicates_module
from gtfs_rt_validator.geometry import buffer as buffer_module
from gtfs_rt_validator.geometry.buffer import within_buffered_shape
from jtsoracle import (
    METRES_PER_DEGREE,
    ORACLE,
    SHAPES,
    TRIP_BUFFER_DEGREES,
    naive_distance,
    probes,
    shallow_probes,
    wiggle,
)


@pytest.mark.parametrize("key", sorted(SHAPES))
def test_ring_probes_match_the_jar(key: str) -> None:
    shape = SHAPES[key][0]
    points = probes(key)
    expected = ORACLE[key]
    assert len(points) == len(expected), "probe geometry drifted from the recorded answers"
    got = "".join(
        "1" if within_buffered_shape(shape, lon, lat, TRIP_BUFFER_DEGREES) else "0"
        for lon, lat in points
    )
    assert got == expected


def test_a_distance_test_would_disagree() -> None:
    """54 of the 420 ring probes sit in the annulus a distance test gets wrong."""
    wrong = 0
    for key, (shape, _centre, _n) in SHAPES.items():
        for expected, (lon, lat) in zip(ORACLE[key], probes(key), strict=True):
            inside_by_distance = naive_distance(shape, lon, lat) <= TRIP_BUFFER_DEGREES
            if inside_by_distance != (expected == "1"):
                wrong += 1
    assert wrong == 54


def test_a_point_in_the_annulus_is_within_the_distance_and_outside_the_buffer() -> None:
    """One of those 54, spelled out. The jar says DISJOINT for this point."""
    shape = SHAPES["straight28"][0]
    lon, lat = -77.00053025493948, 28.001714170066236
    assert naive_distance(shape, lon, lat) < TRIP_BUFFER_DEGREES
    assert within_buffered_shape(shape, lon, lat, TRIP_BUFFER_DEGREES) is False


def test_boundary_counts_as_inside() -> None:
    """A vertex of the jar's own buffer polygon, which `not disjoint` calls CONTAINS."""
    shape = SHAPES["straight28"][0]
    assert within_buffered_shape(shape, -76.97964910259972, 28.001764080358136, TRIP_BUFFER_DEGREES)


def test_the_crossing_count_translates_before_taking_the_determinant() -> None:
    """A point 2.2e-30 outside the leftmost vertex of a round cap. The jar: DISJOINT.

    JTS answers point-in-ring with `RayCrossingCounter`, which subtracts the
    query point from both segment endpoints and only then takes the sign of the
    determinant. `CGAlgorithms.orientationIndex` subtracts consecutive endpoints
    from each other instead, and here that subtraction rounds the gap away
    entirely and reports the point as collinear, which would make it boundary and
    therefore inside. Same predicate, different operands, opposite answer, so the
    crossing counter has to be ported as itself rather than expressed in terms of
    the orientation test used everywhere else in this module.
    """
    shape = [(-77.0, 0.0), (-76.98, 0.0)]
    assert (
        within_buffered_shape(
            shape, -77.00179864073553, 2.2026996195768865e-19, 0.001798640735523327
        )
        is False
    )


# ---------------------------------------------------------------------------
# The input-line simplifier, which moves the boundary further than the chords do
# ---------------------------------------------------------------------------


def test_the_shallow_concave_vertex_is_not_simplified_away() -> None:
    """BufferInputLineSimplifier keeps a vertex it looks like it should delete.

    The vertex deviates from the chord by 0.9 of the `distance / 100` tolerance
    and is concave to the side being simplified, so it clears the shallowness
    test. It survives because `deleteShallowConcavities` never simplifies the end
    segments, and on a three-point line both segments are end segments: the
    sliding window wants indices 1, 2, 3 and there is no index 3. Measured, not
    reasoned: `BufferInputLineSimplifier.simplify` in the jar returns all three
    points for both signed tolerances.

    The answers below are the jar's, for the shape and for the chord the shape
    would collapse to if the vertex went. Four of the eight probes differ, so
    this is not a distinction without an observable difference: dropping the
    vertex moves the buffer boundary by 0.9% of the distance, nearly twice what
    the chord approximation moves it.
    """
    shape = SHAPES["shallow"][0]
    chord = [(-77.0, 28.0), (-76.99, 28.0)]
    got = "".join(
        "1" if within_buffered_shape(shape, lon, lat, TRIP_BUFFER_DEGREES) else "0"
        for lon, lat in shallow_probes()
    )
    if_simplified = "".join(
        "1" if within_buffered_shape(chord, lon, lat, TRIP_BUFFER_DEGREES) else "0"
        for lon, lat in shallow_probes()
    )
    assert got == "11000000"
    assert if_simplified == "11111100"


def test_the_offset_curve_of_a_dense_shape_has_the_length_the_jar_gives_it() -> None:
    """A 24-point shape, the density a real shapes.txt has.

    `BufferInputLineSimplifier.simplify` returns all 24 points for both signed
    tolerances, and `OffsetCurveBuilder.getLineCurve` returns 112 vertices. Both
    numbers came from the jar.

    Vertex 20 is the interesting one: it is concave to the right and 0.54 of a
    tolerance off its neighbours' chord, so it clears both of the first two
    deletion tests and is not protected by the end-segment rule. JTS keeps it
    anyway, because `isDeletable` passes the middle vertex into the parameter
    `isShallowSampled` calls `p2`, so the first sample measures the length of the
    whole first segment instead of a deviation. Porting that call as written
    rather than as intended is the difference between 24 points and 23, and
    between 112 curve vertices and 111.
    """
    tol = TRIP_BUFFER_DEGREES / 100
    assert len(buffer_module._simplify(wiggle(), tol)) == 24
    assert len(buffer_module._simplify(wiggle(), -tol)) == 24
    curve = buffer_module._buffer_curve(wiggle(), TRIP_BUFFER_DEGREES)
    assert len(curve) == 112


# ---------------------------------------------------------------------------
# Degenerate shapes, each pinned to what the jar does with it
# ---------------------------------------------------------------------------


def test_a_one_point_shape_raises() -> None:
    """The jar throws IllegalArgumentException building the LineString, before buffering."""
    with pytest.raises(ValueError, match="one-point shape"):
        within_buffered_shape([(-77.0, 28.0)], -77.0, 28.0, TRIP_BUFFER_DEGREES)


def test_an_empty_shape_is_disjoint_from_everything() -> None:
    """An empty LineString buffers to an empty polygon; the jar answers DISJOINT."""
    assert within_buffered_shape([], -77.0, 28.0, TRIP_BUFFER_DEGREES) is False


@pytest.mark.parametrize("distance", [0.0, -0.001])
def test_a_non_positive_distance_buffers_to_nothing(distance: float) -> None:
    assert within_buffered_shape([(-77.0, 28.0), (-76.98, 28.0)], -77.0, 28.0, distance) is False


def test_repeated_points_collapse_to_a_circle() -> None:
    """Every point identical: removeRepeatedPoints leaves one, and the cap is a full circle."""
    shape = [(-77.0, 28.0)] * 5
    assert within_buffered_shape(
        shape, -77.0 + 0.9 * TRIP_BUFFER_DEGREES, 28.0, TRIP_BUFFER_DEGREES
    )
    assert not within_buffered_shape(
        shape, -77.0 + 1.001 * TRIP_BUFFER_DEGREES, 28.0, TRIP_BUFFER_DEGREES
    )


# ---------------------------------------------------------------------------
# The geography, which upstream gets wrong on purpose here
# ---------------------------------------------------------------------------


def test_the_buffer_is_degrees_and_shrinks_east_west_with_latitude() -> None:
    """200 m north-south everywhere, 176.6 m east-west at 28 N, 128.6 m at 50 N.

    The E029 occurrence text says "more than 200.0 meters" regardless. Compat
    reproduces the error; this test exists so nobody quietly corrects it.
    """
    north_south = TRIP_BUFFER_DEGREES * METRES_PER_DEGREE
    assert round(north_south, 1) == 200.0
    east_west = {
        lat: round(north_south * math.cos(math.radians(lat)), 1) for lat in (0.0, 28.0, 50.0)
    }
    assert east_west == {0.0: 200.0, 28.0: 176.6, 50.0: 128.6}
    # And the code really does treat both directions as the same number of
    # degrees: the same offset is inside at both latitudes.
    for lat in (28.0, 50.0):
        shape = [(-77.0, lat), (-76.98, lat)]
        offset = 0.99 * TRIP_BUFFER_DEGREES
        assert within_buffered_shape(shape, -76.99, lat + offset, TRIP_BUFFER_DEGREES)
        assert within_buffered_shape(shape, -77.0 - offset, lat, TRIP_BUFFER_DEGREES)


# ---------------------------------------------------------------------------
# Constraints and known divergences
# ---------------------------------------------------------------------------


def test_buffer_imports_only_the_standard_library() -> None:
    """No third party, and nothing from the sibling gtfs-validator either.

    `tests/test_no_runtime_dependency.py` permits `gtfs_validator` across `src/`.
    This module is stricter: the JTS reproduction has to stand on its own, so
    reaching into the sibling's geometry package is not an option here.

    The rule covers every module the port is split across, not just the one
    holding the entry point. The only non-stdlib import any of them is allowed is
    another module of the split, which is why those are skipped below.
    """
    port = (buffer_module, offset_curve_module, predicates_module)
    own = {module.__name__ for module in port}
    for module in port:
        path = module.__file__
        assert path is not None
        source = Path(path).read_text(encoding="utf-8")
        roots = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module not in own:
                roots.add((node.module or "").split(".")[0])
        assert roots
        assert roots <= sys.stdlib_module_names, sorted(roots - sys.stdlib_module_names)


def test_known_divergence_one_ulp_from_a_cap_vertex() -> None:
    """A point the jar calls DISJOINT and this module calls inside.

    The point is a vertex of the reproduced offset curve, and the jar's own
    vertex sits one ulp away, because HotSpot's x86-64 `Math.sin`/`Math.cos`
    intrinsic is not the same function as `StrictMath`'s fdlibm, which is what
    Python's libm agrees with. Re-running the differential with `--fdlibm`,
    which disables the intrinsic, makes the offset curves identical bit for bit
    **on the differential's corpus** and makes this case agree.

    Not in general, and an earlier version of this docstring overstated it. An
    audit minimised a two-point line whose curve still differs by one ulp with
    the intrinsic off, and the jar answers CONTAINS at that vertex. The claim
    that survives is the narrow one: on the corpus we run, the residual
    default-JVM gap is attributable to the intrinsic rather than to this module.

    Settling it in Python would mean reimplementing the intrinsic, and the
    answer would still depend on which JVM the jar happens to run under, so
    there is nothing here to be right about. The gap is 2.2e-19 degrees, about
    24 picometres.
    """
    shape = [(-77.0, 0.0), (-76.98, 0.0)]
    lon, lat = -77.00166172736189, -0.0006883100102617363
    assert within_buffered_shape(shape, lon, lat, TRIP_BUFFER_DEGREES) is True


def test_known_divergence_at_a_noded_self_intersection() -> None:
    """A point the jar calls CONTAINS and this module calls outside.

    JTS builds its polygon by noding the self-intersecting offset curve, and the
    node coordinates it computes do not lie exactly on the curve they came from.
    This point is one of them, 9.4e-16 degrees off the reproduced curve, about a
    tenth of a nanometre. Closing it would mean noding the curve here too:
    intersect every pair of curve segments with the ported RobustLineIntersector,
    insert the results, and count crossings against the noded ring. The
    arithmetic is already in this module; what is missing is a spatial index, and
    without one the pass is quadratic in a curve that can run to thousands of
    vertices on a real shape.
    """
    shape = [(-77.0, 28.0), (-76.99, 28.01), (-77.0, 28.01), (-76.99, 28.0)]
    lon, lat = -76.99754366212201, 28.005000000000003
    assert within_buffered_shape(shape, lon, lat, TRIP_BUFFER_DEGREES) is False
