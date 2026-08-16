"""Differential: this project's geometry against the two jars that define it.

Two halves, one per rule, each with its own Java oracle.

- JTS 1.13 through `tools/DumpJtsBuffer.java`, for E029's trip-shape buffer:
  the raw offset curve vertex by vertex, containment over a generated corpus,
  and containment at every vertex and edge midpoint of the jar's own buffer
  polygon, shell rings and hole rings alike.
- spatial4j 0.6 through `tools/DumpSpatial4jBoxes.java`, for E028's bounding
  box: the raw box, the buffered box, and containment answers, over a corpus
  covering every branch of `RectangleImpl.getBuffered` plus a latitude sweep.

A red diff is the deliverable, not an obstacle. Divergences print with the exact
inputs needed to reproduce them, and the harness exits non-zero if either half
diverges. They are split into two categories that are never merged: `HARD` is an
algorithm difference, `ULP` is the last-bit gap between Java's fdlibm and
CPython's platform libm. Nothing is swallowed by a tolerance; `tools/geoulp.py`
says where the line sits and why.

Comparison and the driver live here; the corpora are in `tools/geocorpus.py` and
`tools/geoboxes.py`, and everything that runs a JVM is in `tools/geooracle.py`.

Run:
    .venv/bin/python tools/diff_geometry_against_java.py            # both, as --all
    .venv/bin/python tools/diff_geometry_against_java.py --curves   # offset curves
    .venv/bin/python tools/diff_geometry_against_java.py --contains # JTS containment
    .venv/bin/python tools/diff_geometry_against_java.py --bbox     # spatial4j only
    .venv/bin/python tools/diff_geometry_against_java.py --fdlibm --all
"""

from __future__ import annotations

import importlib
import math
import pkgutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import geoboxes  # noqa: E402
import geocorpus  # noqa: E402
import geooracle  # noqa: E402
from geoboxes import BoxCase  # noqa: E402
from geocorpus import Case  # noqa: E402
from geoulp import Tally  # noqa: E402

from gtfs_rt_validator import geometry  # noqa: E402
from gtfs_rt_validator.geometry import REGION_BUFFER_DEGREES, Rectangle  # noqa: E402
from gtfs_rt_validator.geometry.buffer import within_buffered_shape  # noqa: E402

BOX_KEYS = ("min_x", "max_x", "min_y", "max_y")

JTS_NOTE = """  --fdlibm turns HotSpot's Math.sin/Math.cos intrinsic off and makes the raw
  offset curves bit-identical on this corpus, which is what attributes the
  residual default-JVM gap to the JVM rather than to buffer.py. On this corpus,
  not in general: a two-point line exists whose curve still differs by one ulp
  with the intrinsic off, and the jar answers CONTAINS at that vertex."""

S4J_NOTE = """  ULP rows are the recorded fdlibm divergence: Java's Math is fdlibm here and
  CPython's is the platform libm, so a buffered longitude can land one or two
  ulps away, and a probe placed exactly on such a bound flips with it.
  tests/test_bbox.py pins that as a non-strict xfail. A HARD row is not that,
  and a HARD containment row is an algorithm difference."""


def offset_curve_fn():
    """`_buffer_curve`, found by scanning the geometry package rather than imported.

    It is private, and a concurrent task is splitting `buffer.py` across several
    private modules, so a hard-coded import would break on a reshuffle that
    changes no behaviour. Everything else this script uses is public.
    """
    for info in pkgutil.iter_modules(geometry.__path__):
        module = importlib.import_module(f"{geometry.__name__}.{info.name}")
        found = getattr(module, "_buffer_curve", None)
        if found is not None:
            return found
    raise SystemExit("no module under gtfs_rt_validator.geometry defines _buffer_curve")


# ---------------------------------------------------------------------------
# JTS half: E029's trip-shape buffer
# ---------------------------------------------------------------------------


def diff_containment(cases: list[Case], label: str) -> Tally:
    answers = geooracle.run_jts(cases, "--contains")
    tally = Tally(label, "cases")
    for name, shape, lon, lat, dist in cases:
        where = f"{name} shape={shape!r} lon={lon!r} lat={lat!r} d={dist!r}"
        rows = answers.get(name)
        if not rows:
            tally.fail(where, "the jar returned no answer")
            continue
        if rows[0][0] == "ERROR":
            # Fail closed. An oracle error compared nothing, so counting it as a
            # pass would let a corpus that errored on every case print MATCH.
            tally.fail(where, f"the jar errored: {' '.join(rows[0][1:])}")
            continue
        got = within_buffered_shape(shape, lon, lat, dist)
        tally.answer(where, "contains", rows[0][0] == "CONTAINS", got)
    tally.report()
    return tally


def diff_curves(cases: list[Case]) -> Tally:
    """Compare the raw offset curve, one shape per distinct geometry, vertex by vertex.

    Every coordinate is compared exactly. An earlier version compared only the
    vertex count and reduced the coordinates to a display-only maximum
    deviation, so it reported 0 divergent while the coordinates in fact differed
    by an ulp. A comparison weakened until it passes is not a differential.
    """
    shapes = geocorpus.distinct_shapes(cases)
    answers = geooracle.run_jts(shapes, "--curve")
    curve = offset_curve_fn()
    tally = Tally("offset curves", "vertex coordinates")
    for name, shape, _lon, _lat, dist in shapes:
        where = f"{name} shape={shape!r} d={dist!r}"
        rows = answers.get(name)
        if not rows or rows[0][0] != "CURVE":
            tally.fail(where, f"the jar gave {rows[0] if rows else None}")
            continue
        java_pts = geooracle.points_of(rows[0][1:])
        py_pts = curve(shape, dist)
        if len(java_pts) != len(py_pts):
            tally.fail(where, f"{len(java_pts)} java vertices vs {len(py_pts)} python")
            continue
        for i, (jp, pp) in enumerate(zip(java_pts, py_pts, strict=True)):
            tally.value(f"{where} v{i}", "x", jp[0], pp[0])
            tally.value(f"{where} v{i}", "y", jp[1], pp[1])
    print(f"distinct shapes the offset curve is compared over: {len(shapes)}")
    tally.report()
    return tally


def boundary_cases(cases: list[Case]) -> list[Case]:
    """Probe the jar's own polygon vertices and edge midpoints.

    A point exactly on the boundary counts as CONTAINS, so these are the cases
    where an off-by-one-ulp reconstruction of a ring shows up as a wrong answer
    rather than as a rounding difference nobody can observe. Hole rings are
    boundary too: `disjoint` is false on either ring, and the self-crossing
    shapes in the corpus really do buffer to a polygon with a hole.
    """
    shapes = geocorpus.distinct_shapes(cases)
    rings = geooracle.run_jts(shapes, "--poly")
    out: list[Case] = []
    for name, shape, _lon, _lat, dist in shapes:
        for r, row in enumerate(rings.get(name, [])):
            if row[0] not in ("POLY", "HOLE") or len(row) < 2 or row[1] == "EMPTY":
                continue
            pts = geooracle.points_of(row[1:])
            for i, pt in enumerate(pts):
                nxt = pts[(i + 1) % len(pts)]
                out.append((f"bnd.{name}.r{r}.v{i}", shape, pt[0], pt[1], dist))
                mid = ((pt[0] + nxt[0]) / 2, (pt[1] + nxt[1]) / 2)
                out.append((f"bnd.{name}.r{r}.m{i}", shape, mid[0], mid[1], dist))
    return out


# ---------------------------------------------------------------------------
# spatial4j half: E028's bounding box
# ---------------------------------------------------------------------------


def diff_boxes(cases: list[BoxCase], label: str) -> tuple[list[Tally], dict[str, dict[str, str]]]:
    answers = geooracle.run_boxes(cases)
    bounds = Tally(f"{label} bounds", "bound values")
    inside = Tally(f"{label} containment", "answers")
    for name, points, d, _probes in cases:
        where = f"{name} points={points!r} buffer={d!r}"
        fields = answers.get(name)
        if fields is None or "error" in fields:
            bounds.fail(where, fields["error"] if fields else "the jar returned no answer")
            continue
        raw = Rectangle.from_points(points)
        boxes = {"raw": raw, "buffered": raw.buffered(d)}
        # Bounds that diverged at ulp level, by jar value, so a containment flip
        # exactly on one of them is attributed to that same gap rather than
        # counted a second time as an independent algorithm difference.
        noisy: dict[str, set[float]] = {"raw": set(), "buffered": set()}
        for which, rect in boxes.items():
            java_vals = [float(v) for v in fields[which].split(",")]
            py_vals = [rect.min_x, rect.max_x, rect.min_y, rect.max_y]
            for key, jv, pv in zip(BOX_KEYS, java_vals, py_vals, strict=True):
                seen = len(bounds.ulp)
                bounds.value(f"{where} {which}", key, jv, pv)
                if len(bounds.ulp) > seen:
                    noisy[which].add(jv)
        for record in filter(None, fields["tests"].split("|")):
            lon_s, lat_s, in_raw, in_buffered = record.split(",")
            lon, lat = float(lon_s), float(lat_s)
            for which, want in (("raw", in_raw), ("buffered", in_buffered)):
                inside.answer(
                    f"{where} {which} lon={lon!r} lat={lat!r}",
                    "contains",
                    want == "true",
                    boxes[which].contains(lon, lat),
                    on_ulp_bound=lon in noisy[which] or lat in noisy[which],
                )
    bounds.report()
    inside.report()
    return [bounds, inside], answers


def box_boundary_cases(cases: list[BoxCase], answers: dict[str, dict[str, str]]) -> list[BoxCase]:
    """Re-probe each box exactly at the bounds the jar reported.

    The boundary is inclusive, so this is where a bound that is an ulp out stops
    being invisible and starts flipping an answer, which is the observable
    effect tests/test_bbox.py describes.
    """
    out: list[BoxCase] = []
    for name, points, d, _probes in cases:
        fields = answers.get(name)
        if fields is None or "error" in fields:
            continue
        probes: list[tuple[float, float]] = []
        for which in ("raw", "buffered"):
            min_x, max_x, min_y, max_y = (float(v) for v in fields[which].split(","))
            if math.isnan(min_x):
                continue
            mid_y = (min_y + max_y) / 2
            probes += [(min_x, min_y), (min_x, max_y), (max_x, min_y), (max_x, max_y)]
            probes += [(min_x, mid_y), (max_x, mid_y)]
        if probes:
            out.append((f"bnd.{name}", points, d, probes))
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def summarise(halves: list[tuple[str, list[Tally], str]]) -> int:
    print("\n=== summary ===")
    status = 0
    for label, group, note in halves:
        if not group:
            continue
        bad = max(t.status() for t in group)
        status |= bad
        print(f"{label}: {'DIFF' if bad else 'MATCH'}")
        for tally in group:
            print(f"  {tally.summary()}")
        print(note)
    print(f"exit status {status}; non-zero means at least one half diverged.")
    return status


def run_jts_half(flags: set[str], everything: bool) -> list[Tally]:
    print("--- JTS 1.13, E029's trip-shape buffer ---")
    cases = geocorpus.build_corpus()
    out: list[Tally] = []
    if everything or "--curves" in flags:
        out.append(diff_curves(cases))
    if everything or "--contains" in flags:
        out.append(diff_containment(cases, "containment"))
        bnd = boundary_cases(cases)
        print(f"boundary probes derived from the jar's own polygon: {len(bnd)}")
        out.append(diff_containment(bnd, "boundary probes"))
    return out


def run_bbox_half() -> list[Tally]:
    print("--- spatial4j 0.6, E028's stop and shape bounding box ---")
    cases = geoboxes.build_box_corpus()
    tallies, answers = diff_boxes(cases, "corpus")
    probes = box_boundary_cases(cases, answers)
    print(f"boundary probes derived from the jar's own bounds: {len(probes)}")
    return tallies + diff_boxes(probes, "boundary")[0]


def main() -> None:
    flags = set(sys.argv[1:])
    if "--fdlibm" in flags:
        geooracle.enable_fdlibm()
        flags.discard("--fdlibm")
    if geocorpus.REGION_BUFFER_DEGREES != REGION_BUFFER_DEGREES:
        raise SystemExit("the corpus buffer constant no longer matches geometry's")
    everything = not flags or "--all" in flags
    jts = (
        run_jts_half(flags, everything) if everything or {"--curves", "--contains"} & flags else []
    )
    s4j = run_bbox_half() if everything or "--bbox" in flags else []
    halves = [
        ("JTS com.vividsolutions:jts:1.13, E029's buffer", jts, JTS_NOTE),
        ("spatial4j org.locationtech.spatial4j:0.6, E028's box", s4j, S4J_NOTE),
    ]
    sys.exit(summarise(halves))


if __name__ == "__main__":
    main()
