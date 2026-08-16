"""The JTS buffer corpus for `tools/diff_geometry_against_java.py`.

`build_corpus` produces cases of `(name, shape, lon, lat, distance)`, aimed at
what distinguishes a faithful reproduction of JTS's buffer from a
distance-to-polyline shortcut: the chord annulus, the simplifier threshold, the
inside-turn closing segment.

Split out of the harness when it grew a second oracle, because the repo caps a
file at 300 lines and generation and comparison are the natural seam. Nothing
here imports the package under test, so a corpus is a fact about the geometry
rather than about our reproduction of it. `tools/geoboxes.py` is the same idea
for the spatial4j bounding box.
"""

from __future__ import annotations

import math

# GtfsMetadata.java:45 and :122. Spelled out rather than imported so the corpus
# stays independent of the module it is used to test; the harness checks they
# still equal the package's own constants.
TRIP_BUFFER_DEGREES = 0.001798640735523327
REGION_BUFFER_DEGREES = 0.014470064717285165

# A chord of a fillet lies inside its arc, so the polygon falls short of the true
# offset by this factor at the middle of each chord. Points between COS_HALF * d
# and d are inside the ideal buffer and outside the one JTS computes, which is
# the annulus a distance test gets wrong.
COS_HALF_QUANTUM = math.cos(math.pi / 32)

Case = tuple[str, list[tuple[float, float]], float, float, float]


# ---------------------------------------------------------------------------
# JTS buffer corpus
# ---------------------------------------------------------------------------

# Radii as fractions of the buffer distance. The cluster around COS_HALF_QUANTUM
# and 1.0 is the whole point: that is where the chord approximation and the
# boundary live.
RADIUS_FRACTIONS = (
    0.5,
    0.9,
    COS_HALF_QUANTUM - 0.002,
    COS_HALF_QUANTUM - 1e-9,
    COS_HALF_QUANTUM,
    COS_HALF_QUANTUM + 1e-9,
    (COS_HALF_QUANTUM + 1.0) / 2,
    0.999,
    1.0 - 1e-12,
    1.0,
    1.0 + 1e-12,
    1.001,
    1.1,
)


def ring_probe(
    name: str,
    shape: list[tuple[float, float]],
    centre: tuple[float, float],
    n_angles: int,
    distance: float = TRIP_BUFFER_DEGREES,
    fractions: tuple[float, ...] = RADIUS_FRACTIONS,
) -> list[Case]:
    """Sample a full circle of radii around `centre`, in degrees, not metres."""
    cases: list[Case] = []
    for i in range(n_angles):
        angle = 2 * math.pi * i / n_angles
        for j, frac in enumerate(fractions):
            r = frac * distance
            cases.append(
                (
                    f"{name}.a{i}.r{j}",
                    shape,
                    centre[0] + r * math.cos(angle),
                    centre[1] + r * math.sin(angle),
                    distance,
                )
            )
    return cases


def straight_cases() -> list[Case]:
    """Two-point shapes at real latitudes, probed at both cap and flank.

    The east-west buffer is the same number of degrees at every latitude, which
    is upstream's bug; the corpus spans latitudes so that a latitude correction
    smuggled into the Python would show up here as a diff.
    """
    cases: list[Case] = []
    for lat in (0.0, 28.0, 50.0, 60.0, -33.87):
        shape = [(-77.0, lat), (-76.98, lat)]
        cases += ring_probe(f"straight.lat{lat}.end", shape, (-77.0, lat), 48)
        cases += ring_probe(f"straight.lat{lat}.mid", shape, (-76.99, lat), 16)
    # A segment shorter than the buffer distance: the two caps dominate.
    short = [(-77.0, 28.0), (-77.0 + TRIP_BUFFER_DEGREES / 4, 28.0)]
    cases += ring_probe("straight.short", short, short[1], 48)
    # A diagonal, so no cap or fillet angle lands on a multiple of pi/2.
    diag = [(-77.0, 28.0), (-77.0 + 0.01, 28.0 + 0.007)]
    cases += ring_probe("straight.diag", diag, diag[1], 48)
    return cases


def corner_cases() -> list[Case]:
    """Right-angle, obtuse and acute corners, probed on both sides of the vertex."""
    cases: list[Case] = []
    corners = {
        "right": (-77.0 + 0.01, 28.0 + 0.01),
        "obtuse": (-77.0 + 0.01, 28.0 + 0.003),
        "acute": (-77.0 + 0.001, 28.0 + 0.01),
    }
    for name, tail in corners.items():
        vertex = (-77.0 + 0.01, 28.0)
        shape = [(-77.0, 28.0), vertex, tail]
        cases += ring_probe(f"corner.{name}", shape, vertex, 96)
        # Mirror the turn so the convex side changes hands, which swaps which of
        # the two simplifier passes can delete the vertex.
        mirrored = [(-77.0, 28.0), vertex, (tail[0], 28.0 - (tail[1] - 28.0))]
        cases += ring_probe(f"corner.{name}.mirror", mirrored, vertex, 96)
    return cases


def shallow_concavity_cases() -> list[Case]:
    """Vertices near BufferInputLineSimplifier's `distance / 100` deletion threshold.

    A vertex deviating by less than the tolerance on the simplified side is
    deleted before offsetting, so the polygon bulges past the true offset there.
    The deviations straddle the threshold from both directions.
    """
    cases: list[Case] = []
    tol = TRIP_BUFFER_DEGREES / 100
    for k, factor in enumerate((0.2, 0.5, 0.9, 0.999, 1.0, 1.001, 1.1, 2.0, 5.0)):
        for sign in (1, -1):
            dev = sign * factor * tol
            vertex = (-77.0 + 0.005, 28.0 + dev)
            shape = [(-77.0, 28.0), vertex, (-77.0 + 0.01, 28.0)]
            cases += ring_probe(f"shallow.f{k}.s{sign}", shape, vertex, 64)
    return cases


def pathological_cases() -> list[Case]:
    """Self-intersection, duplicates, collapse to a point, and narrow spikes."""
    cases: list[Case] = []

    crossing = [(-77.0, 28.0), (-76.99, 28.01), (-77.0, 28.01), (-76.99, 28.0)]
    cases += ring_probe("cross.node", crossing, (-76.995, 28.005), 96)
    cases += ring_probe("cross.end", crossing, crossing[0], 48)

    dupes = [
        (-77.0, 28.0),
        (-77.0, 28.0),
        (-76.99, 28.0),
        (-76.99, 28.0),
        (-76.99, 28.0),
        (-76.985, 28.004),
    ]
    cases += ring_probe("dupes.mid", dupes, (-76.99, 28.0), 64)

    same = [(-77.0, 28.0)] * 5
    cases += ring_probe("identical", same, (-77.0, 28.0), 64)

    two_identical = [(-77.0, 28.0), (-77.0, 28.0)]
    cases += ring_probe("identical.two", two_identical, (-77.0, 28.0), 32)

    # Doubles back along its own line: the collinear-reversal branch, which adds
    # a full fillet where an ordinary corner adds part of one.
    spur = [(-77.0, 28.0), (-76.99, 28.0), (-76.995, 28.0)]
    cases += ring_probe("reversal", spur, (-76.99, 28.0), 64)

    # A spike so narrow that the offset segments never meet, which is the
    # closing-segment branch of addInsideTurn.
    spike = [(-77.0, 28.0), (-76.9999, 28.004), (-76.99978, 28.0)]
    cases += ring_probe("spike.tip", spike, (-76.9999, 28.004), 64)
    cases += ring_probe("spike.gap", spike, (-76.99989, 28.002), 64)

    # A dense wiggly line, the shape a real GTFS shapes.txt produces: enough
    # vertices for the simplifier to run several passes.
    wiggle = [
        (-77.0 + 0.001 * i, 28.0 + 0.0004 * math.sin(i * 1.1) + 0.00002 * math.cos(i * 5.0))
        for i in range(24)
    ]
    cases += ring_probe("wiggle.mid", wiggle, wiggle[12], 64)
    cases += ring_probe("wiggle.end", wiggle, wiggle[-1], 48)
    return cases


def build_corpus() -> list[Case]:
    return straight_cases() + corner_cases() + shallow_concavity_cases() + pathological_cases()


def encode(shape: list[tuple[float, float]]) -> str:
    """One shape, in DumpJtsBuffer's tab-delimited wire format."""
    return ";".join(f"{x!r},{y!r}" for x, y in shape)


def distinct_shapes(cases: list[Case]) -> list[Case]:
    """One case per distinct geometry, renamed so ids stay unique per shape."""
    seen: dict[str, Case] = {}
    for _name, shape, lon, lat, dist in cases:
        key = encode(shape)
        if key not in seen:
            seen[key] = (f"shape{len(seen)}", shape, lon, lat, dist)
    return list(seen.values())
