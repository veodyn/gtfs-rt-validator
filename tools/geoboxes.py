"""The spatial4j bounding-box corpus for `tools/diff_geometry_against_java.py`.

`build_box_corpus` produces cases of `(name, points, buffer, probes)`, covering
every branch `RectangleImpl.getBuffered` takes (both pole clamps, the
world-wrap-by-buffer test, the ordinary case) and every branch the multipoint
envelope takes before it (the widest-gap search for a span over 180 degrees),
plus a 3000-case latitude sweep.

The sweep is there because the one recorded divergence is a one-to-two ulp libm
gap that a dozen hand-picked latitudes would miss. It reproduces the methodology
that found the gap rather than hoping it reappears.

`render_box_corpus` writes the directive grammar `DumpSpatial4jBoxes.java`
parses. Nothing here imports the package under test.
"""

from __future__ import annotations

from geocorpus import REGION_BUFFER_DEGREES, TRIP_BUFFER_DEGREES

BoxCase = tuple[str, list[tuple[float, float]], float, list[tuple[float, float]]]

# Multiples of the buffer distance to step out from each edge of the raw box.
BOX_PROBE_FRACTIONS = (0.0, 0.5, 0.999, 1.0, 1.001, 1.5, 2.0)

R = REGION_BUFFER_DEGREES

NAMED_BOX_SETS: tuple[tuple[str, list[tuple[float, float]], float], ...] = (
    ("equator", [(0.0, 0.0), (0.1, 0.05)], R),
    ("equator.tripbuffer", [(-78.5, -0.2), (-78.4, 0.1)], TRIP_BUFFER_DEGREES),
    ("midlat", [(-82.5, 27.95), (-82.4, 28.05)], R),
    ("midlat.zerobuffer", [(-1.0, 51.5), (1.0, 51.6)], 0.0),
    ("midlat.south", [(151.1, -33.95), (151.3, -33.8)], R),
    ("highlat", [(18.0, 69.6), (18.2, 69.7)], R),
    ("extremelat", [(0.0, 89.9), (1.0, 89.98)], R),
    ("northpole", [(10.0, 89.99), (-170.0, 89.995)], R),
    ("southpole", [(10.0, -89.99), (-170.0, -89.995)], R),
    ("antimeridian", [(179.9, -16.5), (-179.9, -16.6)], R),
    ("antimeridian.gapelsewhere", [(179.9, -16.5), (-179.9, -16.6), (10.0, -16.55)], R),
    ("singlepoint", [(-122.4, 37.8)], R),
    # The latitude tests/test_bbox.py pins: the jar's min_x is two ulps outside
    # ours here, and it is the only case in the file that is expected to diverge.
    ("singlepoint.divergent", [(0.0, 20.0295)], R),
    ("duplicatepoints", [(5.0, 45.0), (5.0, 45.0), (5.0, 45.0)], R),
    ("worldwrapbybuffer", [(-179.999, 10.0), (179.999, 10.1), (0.0, 10.05)], R),
    # 270 degrees wide at 89.98 N: the longitude buffer alone is 46 degrees a
    # side, so `lon_distance * 2 + width >= 360` fires without either pole clamp.
    ("nearpole.wrapbybuffer", [(-135.0, 89.9), (0.0, 89.95), (135.0, 89.98)], R),
    ("fullwidth", [(-180.0, -5.0), (180.0, 5.0), (0.0, 0.0)], R),
    ("widenowrap", [(-100.0, 20.0), (100.0, 30.0), (0.0, 25.0)], R),
    # No stop had both coordinates: bounds are NaN and containment must answer
    # False for every probe without raising.
    ("degenerate", [], R),
)


def _wrap_lon(lon: float) -> float:
    """Keep a probe inside +/-180, which is where `pointXY` stops throwing."""
    return (lon + 180.0) % 360.0 - 180.0


def box_probes(points: list[tuple[float, float]], d: float) -> list[tuple[float, float]]:
    """Probe the input points, the centre, and each edge stepped out by `f * d`."""
    if not points:
        return [(0.0, 0.0), (-82.45, 28.0), (180.0, 90.0), (-180.0, -90.0)]
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    lo_x, hi_x, lo_y, hi_y = min(lons), max(lons), min(lats), max(lats)
    mid_x, mid_y = _wrap_lon((lo_x + hi_x) / 2), (lo_y + hi_y) / 2
    probes = [*points, (mid_x, mid_y)]
    for f in BOX_PROBE_FRACTIONS:
        probes.append((_wrap_lon(lo_x - f * d), mid_y))
        probes.append((_wrap_lon(hi_x + f * d), mid_y))
        probes.append((mid_x, max(-90.0, lo_y - f * d)))
        probes.append((mid_x, min(90.0, hi_y + f * d)))
    return probes


def sweep_box_cases(n: int = 3000, start: float = 20.0, step: float = 0.01) -> list[BoxCase]:
    """Single-point boxes marching north, the sweep that found the ulp gap.

    Deliberately 3000 cases from 20 N, matching the randomised sweep recorded in
    `tests/test_bbox.py`, so the count of ulp divergences the harness reports is
    comparable with the count already written down there.
    """
    cases: list[BoxCase] = []
    for i in range(n):
        lat = start + step * i
        probes = [(0.0, lat + f * R) for f in (0.0, 1.0, 1.001, -1.0, -1.001)]
        cases.append((f"sweep{i}", [(0.0, lat)], R, probes))
    return cases


def build_box_corpus() -> list[BoxCase]:
    named = [(name, pts, d, box_probes(pts, d)) for name, pts, d in NAMED_BOX_SETS]
    return named + sweep_box_cases()


def render_box_corpus(cases: list[BoxCase]) -> str:
    """DumpSpatial4jBoxes' directive grammar. `repr` round-trips through Java."""
    out: list[str] = []
    for name, points, d, probes in cases:
        out.append(f"case {name}")
        out += [f"point {lon!r} {lat!r}" for lon, lat in points]
        out.append(f"buffer {d!r}")
        out += [f"test {lon!r} {lat!r}" for lon, lat in probes]
        out.append("end")
    return "\n".join(out) + "\n"
