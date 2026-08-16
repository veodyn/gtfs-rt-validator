"""`_shared/geodesic.py`, against closed forms and against Vincenty's inverse.

The module's docstring states an error bound, and a stated bound nobody
evaluated is a guess. So the oracle lives here: `vincenty_meters` below is
Vincenty's 1975 inverse solution on the WGS-84 ellipsoid, accurate to well under
a millimetre for anything but a near-antipodal pair, and it is a genuinely
different formulation from the one under test. That one converts to
earth-centred coordinates and flattens a tangent plane; this one iterates on an
auxiliary sphere and never builds a coordinate at all. Agreement between them is
therefore evidence rather than a tautology.

The oracle is checked too, against two values that need no implementation. The
equator is a geodesic, so a degree of longitude on it is exactly
`a * pi / 180 = 111319.4908 m`. A degree of latitude is a meridian arc, which
`meridian_arc_meters` integrates by Gauss-Legendre quadrature over the
meridional radius of curvature: a third formulation, and the one that says the
familiar 110574 m is not a number this file copied from anywhere.
"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from gtfs_rt_validator.rules._shared.geodesic import (
    WGS84_FLATTENING,
    WGS84_SEMI_MAJOR_METERS,
    distance_to_point,
    distance_to_polyline,
)

A = WGS84_SEMI_MAJOR_METERS
F = WGS84_FLATTENING
B = (1 - F) * A
E2 = F * (2 - F)


def vincenty_meters(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Vincenty's inverse solution. `(lon, lat)` degrees, metres out."""
    u1 = math.atan((1 - F) * math.tan(math.radians(lat1)))
    u2 = math.atan((1 - F) * math.tan(math.radians(lat2)))
    ell = math.radians(lon2 - lon1)
    su1, cu1, su2, cu2 = math.sin(u1), math.cos(u1), math.sin(u2), math.cos(u2)
    lam, sin_sigma, cos_sigma, sigma, cos2_alpha, cos_2sm = ell, 0.0, 0.0, 0.0, 0.0, 0.0
    for _ in range(200):
        sl, cl = math.sin(lam), math.cos(lam)
        sin_sigma = math.hypot(cu2 * sl, cu1 * su2 - su1 * cu2 * cl)
        if sin_sigma == 0:
            return 0.0
        cos_sigma = su1 * su2 + cu1 * cu2 * cl
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = cu1 * cu2 * sl / sin_sigma
        cos2_alpha = 1 - sin_alpha * sin_alpha
        cos_2sm = cos_sigma - 2 * su1 * su2 / cos2_alpha if cos2_alpha != 0 else 0.0
        c = F / 16 * cos2_alpha * (4 + F * (4 - 3 * cos2_alpha))
        was = lam
        lam = ell + (1 - c) * F * sin_alpha * (
            sigma + c * sin_sigma * (cos_2sm + c * cos_sigma * (2 * cos_2sm * cos_2sm - 1))
        )
        if abs(lam - was) < 1e-13:
            break
    usq = cos2_alpha * (A * A - B * B) / (B * B)
    big_a = 1 + usq / 16384 * (4096 + usq * (usq * (320 - 175 * usq) - 768))
    big_b = usq / 1024 * (256 + usq * (usq * (74 - 47 * usq) - 128))
    delta = (
        big_b
        * sin_sigma
        * (
            cos_2sm
            + big_b
            / 4
            * (
                cos_sigma * (2 * cos_2sm * cos_2sm - 1)
                - big_b
                / 6
                * cos_2sm
                * (4 * sin_sigma * sin_sigma - 3)
                * (4 * cos_2sm * cos_2sm - 3)
            )
        )
    )
    return B * big_a * (sigma - delta)


def meridian_arc_meters(lat1: float, lat2: float) -> float:
    """The meridian arc, by quadrature over the meridional radius of curvature.

    `M(phi) = a (1 - e2) / (1 - e2 sin^2 phi) ** 1.5`, integrated with a
    five-point Gauss-Legendre rule per degree. Independent of both the module
    and the oracle, and exact to far more digits than either is asserted to.
    """
    nodes = (
        (0.0, 128 / 225),
        (-(1 / 3) * math.sqrt(5 - 2 * math.sqrt(10 / 7)), (322 + 13 * math.sqrt(70)) / 900),
        ((1 / 3) * math.sqrt(5 - 2 * math.sqrt(10 / 7)), (322 + 13 * math.sqrt(70)) / 900),
        (-(1 / 3) * math.sqrt(5 + 2 * math.sqrt(10 / 7)), (322 - 13 * math.sqrt(70)) / 900),
        ((1 / 3) * math.sqrt(5 + 2 * math.sqrt(10 / 7)), (322 - 13 * math.sqrt(70)) / 900),
    )
    total = 0.0
    steps = max(1, int(abs(lat2 - lat1)) * 4)
    edges = [lat1 + (lat2 - lat1) * step / steps for step in range(steps + 1)]
    for low, high in pairwise(edges):
        half = math.radians(high - low) / 2
        middle = math.radians(high + low) / 2
        for node, weight in nodes:
            phi = middle + half * node
            sin_phi = math.sin(phi)
            total += weight * half * A * (1 - E2) / (1 - E2 * sin_phi * sin_phi) ** 1.5
    return total


def test_the_oracle_agrees_with_the_two_closed_forms():
    """The equator is a geodesic and the meridian is one, so both are exact."""
    assert vincenty_meters(0, 0, 1, 0) == pytest.approx(A * math.radians(1), abs=1e-6)
    assert vincenty_meters(0, 0, 0, 1) == pytest.approx(meridian_arc_meters(0, 1), abs=1e-6)
    assert meridian_arc_meters(0, 1) == pytest.approx(110574.389, abs=0.001)


#: A degree of anything is about 111 km, which is the module's 100 km row, so
#: the tangent plane is about 5 m short of the true arc and the tolerance here
#: has to say so. Every assertion below quotes the arc and allows the
#: shortening; a tolerance small enough to hide it would be a tolerance that had
#: stopped measuring anything.
ONE_DEGREE_SHORTENING_METERS = 6.0


def test_a_degree_of_latitude():
    """110.574 km at the equator and 111.421 km at 60 north, because the
    ellipsoid is flatter towards the pole and its meridional curvature gentler.

    Both are the quadrature's own answer rather than a quoted figure, which is
    what makes this an independent check rather than a copy.
    """
    assert distance_to_point((0.0, 1.0), 0.0, 0.0) == pytest.approx(
        meridian_arc_meters(0, 1), abs=ONE_DEGREE_SHORTENING_METERS
    )
    assert distance_to_point((0.0, 61.0), 0.0, 60.0) == pytest.approx(
        meridian_arc_meters(60, 61), abs=ONE_DEGREE_SHORTENING_METERS
    )
    assert meridian_arc_meters(60, 61) == pytest.approx(111420.7, abs=0.1)


def test_a_degree_of_longitude_at_the_equator_and_at_sixty_north():
    """111.32 km and 55.80 km. The second is very nearly half the first, which
    is `cos 60`, and only very nearly, because the prime-vertical radius of
    curvature is larger at 60 north than at the equator.

    The equator is a geodesic, so its degree is exactly `a * pi / 180`. The
    parallel at 60 north is not one, so the oracle answers slightly less than
    the parallel arc of 55800.0 m and this is compared against the oracle.
    """
    assert distance_to_point((1.0, 0.0), 0.0, 0.0) == pytest.approx(
        A * math.radians(1), abs=ONE_DEGREE_SHORTENING_METERS
    )
    assert distance_to_point((1.0, 60.0), 0.0, 60.0) == pytest.approx(
        vincenty_meters(0.0, 60.0, 1.0, 60.0), abs=1.0
    )
    assert vincenty_meters(0.0, 60.0, 1.0, 60.0) == pytest.approx(55799.5, abs=0.1)


def test_a_point_on_a_segment_is_at_zero():
    line = [(0.0, 0.0), (0.0, 0.02)]

    assert distance_to_polyline(line, 0.0, 0.01) == pytest.approx(0.0, abs=1e-6)


def test_a_vertex_is_at_zero():
    line = [(0.0, 0.0), (0.001, 0.0), (0.002, 0.0)]

    assert distance_to_polyline(line, 0.001, 0.0) == pytest.approx(0.0, abs=1e-9)


def test_a_point_beyond_the_end_measures_to_the_endpoint_not_to_the_line():
    """The segment runs one degree east along the equator and stops. A point a
    further degree east is 111 km from the end, and zero from the infinite line
    the segment lies on. The clamp is what makes it the first answer."""
    line = [(0.0, 0.0), (1.0, 0.0)]

    found = distance_to_polyline(line, 2.0, 0.0)

    assert found == pytest.approx(vincenty_meters(1.0, 0.0, 2.0, 0.0), abs=6.0)
    assert found > 111_000


def test_the_nearest_of_several_segments_wins():
    """The query point sits just north of the middle of the second segment, so
    the first segment, which runs away south, must lose.

    The tolerance is 0.1 mm rather than a micrometre because the two vertices
    lie on a parallel and a parallel is not a geodesic: the straight line drawn
    between them passes about 4 micrometres inside it, so the nearest point of
    the segment is that much further away than the point on the parallel.
    """
    line = [(0.0, 0.0), (0.0, 0.01), (0.01, 0.01)]

    assert distance_to_polyline(line, 0.005, 0.0102) == pytest.approx(
        distance_to_point((0.005, 0.01), 0.005, 0.0102), abs=1e-4
    )


def test_a_polyline_with_no_points_is_none_rather_than_infinity():
    """`inf` is greater than any threshold, so a caller that forgot to check
    would report every vehicle on a feed whose shapes decoded to nothing.
    `None` raises at the comparison instead."""
    assert distance_to_polyline([], 0.0, 0.0) is None
    with pytest.raises(TypeError):
        assert distance_to_polyline([], 0.0, 0.0) > 200  # type: ignore[operator]


def test_a_one_point_polyline_is_that_points_distance():
    assert distance_to_polyline([(0.0, 0.0)], 1.0, 0.0) == distance_to_point((0.0, 0.0), 1.0, 0.0)


def test_a_segment_whose_two_points_coincide_is_that_point():
    line = [(0.0, 0.0), (0.0, 0.0)]

    assert distance_to_polyline(line, 0.0, 0.001) == pytest.approx(
        distance_to_point((0.0, 0.0), 0.0, 0.001), abs=1e-9
    )


def test_an_antimeridian_crossing_needs_no_wrapping_rule():
    """Two points 0.001 degrees apart with 359.999 degrees between their
    longitudes. Earth-centred coordinates are global, so this is 111 metres
    because it is, and a formulation that subtracted longitudes would answer
    40,000 km."""
    found = distance_to_point((179.9995, 0.0), -179.9995, 0.0)

    assert found == pytest.approx(vincenty_meters(179.9995, 0.0, -179.9995, 0.0), abs=1e-6)
    assert found == pytest.approx(111.3, abs=0.1)


def test_a_segment_spanning_the_antimeridian_is_measured_across_it():
    line = [(179.99, 0.0), (-179.99, 0.0)]

    assert distance_to_polyline(line, 180.0, 0.0) == pytest.approx(0.0, abs=1e-6)


ERROR_BOUND_METERS = (
    (200.0, 1e-6),
    (1_000.0, 1e-5),
    (10_000.0, 0.005),
    (100_000.0, 4.3),
)


def bearing_offset(lat: float, bearing_deg: float, meters: float) -> tuple[float, float]:
    """A point roughly `meters` away on that bearing, by local scaling.

    Only roughly: the point is fed to both the module and the oracle and the
    two are compared against each other, so where it landed does not have to be
    exact. What matters is that it is spread over every bearing.
    """
    north = meters * math.cos(math.radians(bearing_deg))
    east = meters * math.sin(math.radians(bearing_deg))
    phi = math.radians(lat)
    meridional = A * (1 - E2) / (1 - E2 * math.sin(phi) ** 2) ** 1.5
    prime_vertical = A / math.sqrt(1 - E2 * math.sin(phi) ** 2)
    return (
        math.degrees(east / (prime_vertical * math.cos(phi))),
        lat + math.degrees(north / meridional),
    )


def test_the_error_bound_in_the_docstring_is_the_measured_one():
    """Every latitude from 80 south to 80 north, all 24 bearings, against the
    oracle. The module's table is these numbers; if this fails, that table is
    what has to change, not the tolerance.
    """
    for meters, allowed in ERROR_BOUND_METERS:
        worst = 0.0
        for lat in range(-80, 81, 5):
            for bearing in range(0, 360, 15):
                lon2, lat2 = bearing_offset(float(lat), float(bearing), meters)
                mine = distance_to_point((lon2, lat2), 0.0, float(lat))
                truth = vincenty_meters(0.0, float(lat), lon2, lat2)
                worst = max(worst, abs(mine - truth))
        assert worst <= allowed, f"{meters} m separation was off by {worst} m"


def test_the_error_is_a_shortening_and_never_an_overstatement():
    """It flattens a curve, so it can only ever answer short. P015 therefore
    under-reports at long range rather than inventing a violation, which is the
    direction a rule that only adds notices should err in."""
    for lat in range(-60, 61, 20):
        for bearing in range(0, 360, 45):
            lon2, lat2 = bearing_offset(float(lat), float(bearing), 100_000.0)
            mine = distance_to_point((lon2, lat2), 0.0, float(lat))
            assert mine <= vincenty_meters(0.0, float(lat), lon2, lat2) + 1e-6
