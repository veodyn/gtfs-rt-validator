"""The shapes gate, the four bounding boxes, and the buffered-shape accessor.

Split out of `tests/test_static_context.py` at the 300-line cap, by concern:
everything here is `GtfsMetadata.java:119-150` and `:216-233`, the block
`-ignoreShapes` skips and the block the gate guards.

The gate is the reason this file exists. Upstream's condition is
`shapePoints != null && !ignoreShapes && shapePoints.size() > 3`, and
`shapePoints` is `gtfsData.getAllShapePoints()`, so the count is **feed-wide**
and not per shape. Reading it as per-shape would leave E029 quietly disabled on
every small feed and would move E028's box and its message text, so both sides
of the boundary are pinned here with the points spread across two shapes.

CORRECTION, and it is why the boundary below is 3 against 4 rather than 4
against 5. The gate is repeatedly described in prose, including in earlier
drafts of this project's own notes, as leaving a feed with four or fewer shape
points with no shape data. That contradicts the line those descriptions quote
correctly one sentence earlier: `size() > 3` is true at four, so four points
*open* the gate. `getAllShapePoints()` returns a
`Collection<ShapePoint>` in both the packed and unpacked branches of
`GtfsDaoImpl`, so its size is a count of points and there is no reading under
which four is excluded. Three or fewer is the closed case.
"""

from __future__ import annotations

import math

from gtfs_rt_validator.geometry.bbox import REGION_BUFFER_DEGREES, Rectangle
from gtfs_rt_validator.static.context import TRIP_BUFFER_DEGREES, TRIP_BUFFER_METERS
from gtfsfixtures import minimal_tables
from test_static_context import context_from, stop_time, trip

# The two sides of the gate, both spread over two shapes so that a per-shape
# reading of `size() > 3` would keep the four-point feed shut. The shape points
# also reach further north and east than the stops do, so the shapes box and the
# stops box are different rectangles and a fallback between them is visible.
THREE_POINTS = [("SH1", 1, 27.95, -82.45), ("SH1", 2, 27.97, -82.43)]
THREE_POINTS += [("SH2", 1, 28.01, -82.39)]
FOUR_POINTS = [*THREE_POINTS, ("SH2", 2, 28.09, -82.31)]


def shape_rows(points):
    return [
        {
            "shape_id": shape_id,
            "shape_pt_sequence": str(sequence),
            "shape_pt_lat": f"{lat}",
            "shape_pt_lon": f"{lon}",
        }
        for shape_id, sequence, lat, lon in points
    ]


def two_shape_tables(points):
    """The minimal feed with two shapes, two trips, and `points` in shapes.txt."""
    tables = minimal_tables()
    tables["shapes.txt"] = shape_rows(points)
    tables["trips.txt"].append(dict(trip("T2"), shape_id="SH2"))
    tables["stop_times.txt"].append(stop_time("T2", "S1", "1"))
    return tables


def test_three_shape_points_feed_wide_close_the_gate(tmp_path):
    """`size() > 3` is false at three, so there is no shape data at all."""
    ctx = context_from(tmp_path, two_shape_tables(THREE_POINTS))

    assert ctx.shape_points == {}
    assert ctx.trip_shapes == {}
    assert ctx.shape_bounding_box is None
    assert ctx.shape_bounding_box_buffered is None
    assert ctx.buffered_trip_shape("T1") is None
    assert not ctx.stop_bounding_box.is_empty, "the stops box is outside the gate"


def test_four_shape_points_feed_wide_open_the_gate(tmp_path):
    """The other side of the boundary, and the feed-wideness, in one feed.

    Four points over two shapes: two each. The feed-wide count is 4, which is
    greater than 3, so everything populates. A per-shape reading would compare 2
    against 3 for each list and produce no shape data at all, which is the
    failure this test exists to catch.
    """
    ctx = context_from(tmp_path, two_shape_tables(FOUR_POINTS))

    assert set(ctx.shape_points) == {"SH1", "SH2"}
    assert [len(points) for points in ctx.shape_points.values()] == [2, 2]
    assert set(ctx.trip_shapes) == {"T1", "T2"}
    assert isinstance(ctx.shape_bounding_box, Rectangle)
    assert isinstance(ctx.shape_bounding_box_buffered, Rectangle)
    assert ctx.buffered_trip_shape("T2") is not None


def test_the_gate_counts_points_and_not_shapes(tmp_path):
    """Four shapes of one point each is four points, so the gate opens.

    The sharpest form of the same fact: a per-shape reading sees four lists of
    one and shuts, and the feed-wide count of 4 opens. Upstream then builds a
    one-point `LineString` per trip, which JTS refuses; that crash is upstream's
    and belongs to whichever rule asks for the buffered shape, so this only
    pins where the gate lands.
    """
    points = [(f"SH{i}", 1, 27.95 + i * 0.01, -82.45 + i * 0.01) for i in range(1, 5)]

    ctx = context_from(tmp_path, two_shape_tables(points))

    assert set(ctx.shape_points) == {"SH1", "SH2", "SH3", "SH4"}
    assert ctx.shape_bounding_box is not None


def test_shape_points_are_sorted_by_shape_pt_sequence(tmp_path):
    """`shapePointList.sort(comparing(getSequence))`, run over every list.

    Written to the file out of order. `shape_pt_sequence` is a required field, so
    it can never be `None` here: the sibling marks a table with a missing
    required field UNPARSABLE_ROWS and `load_static` raises before this point.
    """
    scrambled = [("SH1", 3, 28.05, -82.35), ("SH1", 1, 27.95, -82.45)]
    scrambled += [("SH1", 4, 28.07, -82.33), ("SH1", 2, 27.97, -82.43)]
    scrambled += [("SH1", 5, 28.09, -82.31)]

    ctx = context_from(tmp_path, two_shape_tables(scrambled))

    assert [row["shape_pt_sequence"] for row in ctx.shape_points["SH1"]] == [1, 2, 3, 4, 5]
    assert ctx.trip_shapes["T1"][0] == (-82.45, 27.95), "lon first, as spatial4j pointXY takes it"
    assert ctx.trip_shapes["T1"][-1] == (-82.31, 28.09)


def test_a_trip_gets_a_shape_only_when_its_shape_id_resolves(tmp_path):
    """`if (shapeAgencyAndId != null && !isEmpty(id))`, then `mShapePoints.get(id)`.

    An empty `shape_id` cell arrives as `None` from the sibling's loader, which
    is the same branch upstream takes for an absent one. A `shape_id` that names
    no shape simply has no entry, and upstream reaches that state too: the
    onebusaway reader does not treat `trips.shape_id` as a foreign key.
    """
    tables = two_shape_tables(FOUR_POINTS)
    tables["trips.txt"][0]["shape_id"] = None
    tables["trips.txt"].append(dict(trip("T3"), shape_id="MISSING"))
    tables["stop_times.txt"].append(stop_time("T3", "S1", "1"))

    ctx = context_from(tmp_path, tables)

    assert set(ctx.trip_shapes) == {"T2"}
    assert ctx.buffered_trip_shape("T1") is None
    assert ctx.buffered_trip_shape("T3") is None
    assert ctx.buffered_trip_shape("NOT_A_TRIP") is None


def test_trips_on_one_shape_share_the_polyline_object_rather_than_copying_it(tmp_path):
    """Identity, not equality, and the difference is 1.7 GB on a real feed.

    `build_trips` converts a shape's rows into `(lon, lat)` pairs once per
    *trip*, which is the shape upstream's Java has: it walks trips and builds a
    list inside the loop. On the MBTA's archive that is 92,360 trips over 1,157
    distinct shapes, so 393,779 shape points on disk became 25,737,031 tuples
    held for the life of the feed, a factor of 65. Measured at 1.75 GB of the
    3.55 GB a prepared feed retains, which is most of the reason `prepare_feed`
    is a memory commitment at all.

    Sharing is invisible to output, the values being identical either way, so no
    rule and no report can tell whether two trips point at one polyline or two.
    What makes it *safe* is that the polyline is a tuple: `trip_shapes` reaches a
    caller through `PreparedFeed.static`, which may outlive hundreds of runs, and
    a shared list would turn one stray `append` into a change to every trip on
    that shape. The immutability is asserted here rather than assumed, because it
    is the whole argument for sharing.

    `==` would pass against the old per-trip copies, so this asserts `is`.
    """
    tables = two_shape_tables(FOUR_POINTS)
    tables["trips.txt"].append(dict(trip("T3"), shape_id="SH1"))
    tables["stop_times.txt"].append(stop_time("T3", "S1", "1"))

    ctx = context_from(tmp_path, tables)

    assert ctx.trip_shapes["T1"] is ctx.trip_shapes["T3"], "same shape_id, one polyline"
    assert ctx.trip_shapes["T1"] is not ctx.trip_shapes["T2"], "different shape_id, two"
    assert ctx.trip_shapes["T1"] == ((-82.45, 27.95), (-82.43, 27.97))
    assert isinstance(ctx.trip_shapes["T1"], tuple), "shared, so it must not be editable"


def test_the_boxes_are_built_over_the_right_points_and_buffered_by_a_mile(tmp_path):
    """Stops box over every stop with both coordinates; shapes box over every point."""
    tables = two_shape_tables(FOUR_POINTS)

    ctx = context_from(tmp_path, tables)

    stops = Rectangle.from_points([(-82.45, 27.95), (-82.35, 28.05)])
    shapes = Rectangle.from_points([(lon, lat) for _, _, lat, lon in FOUR_POINTS])
    assert ctx.stop_bounding_box == stops
    assert ctx.stop_bounding_box_buffered == stops.buffered(REGION_BUFFER_DEGREES)
    assert ctx.shape_bounding_box == shapes
    assert ctx.shape_bounding_box_buffered == shapes.buffered(REGION_BUFFER_DEGREES)


def test_a_stop_missing_either_coordinate_is_left_out_of_the_box(tmp_path):
    """`if (stop.isLonSet() && stop.isLatSet())`, so one of the two is not enough."""
    tables = minimal_tables()
    tables["stops.txt"][1]["stop_lat"] = None

    ctx = context_from(tmp_path, tables)

    assert ctx.stop_bounding_box == Rectangle(-82.45, -82.45, 27.95, 27.95)
    assert "S2" in ctx.stop_ids, "it is still a stop; it just has no position"


def test_no_coordinates_and_no_shapes_gives_a_degenerate_box_that_never_raises(tmp_path):
    """Measured: `Rect(NaN,NaN,NaN,NaN)`, DISJOINT from every point, no exception.

    So E028 fires for every vehicle position on such a feed, and nothing along
    that path throws. This is the case that would be easy to "fix" into a crash
    or into a box that contains everything, and either would be a parity failure.
    """
    tables = minimal_tables()
    for row in tables["stops.txt"]:
        row["stop_lat"] = None
        row["stop_lon"] = None
    del tables["shapes.txt"]
    tables["trips.txt"][0]["shape_id"] = None

    ctx = context_from(tmp_path, tables)

    assert ctx.stop_bounding_box.is_empty
    assert ctx.stop_bounding_box_buffered.is_empty
    assert math.isnan(ctx.stop_bounding_box.min_x)
    assert ctx.shape_bounding_box is None
    for lon, lat in [(-82.4, 28.0), (0.0, 0.0), (180.0, 90.0)]:
        assert ctx.stop_bounding_box.contains(lon, lat) is False
        assert ctx.stop_bounding_box_buffered.contains(lon, lat) is False


def test_the_buffered_trip_shape_answers_containment_and_is_memoised(tmp_path):
    """`mTripShapesBuffered.computeIfAbsent`: built once, then kept for the run.

    Upstream's cache is a `ConcurrentHashMap` that lives as long as the metadata,
    so it survives every file of an archive replay. Identity is the observable
    part of that here; the cache lifetime shows up in wall clock, never in
    output bytes.
    """
    ctx = context_from(tmp_path, two_shape_tables(FOUR_POINTS))

    shape = ctx.buffered_trip_shape("T1")

    assert shape is ctx.buffered_trip_shape("T1")
    assert shape.distance_degrees == TRIP_BUFFER_DEGREES
    assert shape.points == ((-82.45, 27.95), (-82.43, 27.97))
    assert shape.contains(-82.45, 27.95) is True, "a shape vertex is inside its own buffer"
    # SH1 runs north-east at 45 degrees, so the perpendicular offset from its
    # midpoint is (1, -1) / sqrt(2). Half a buffer out is inside and two buffers
    # out is outside, both far enough from the boundary that the chord
    # approximation `geometry/buffer.py` reproduces cannot decide either.
    step = math.sqrt(0.5) * TRIP_BUFFER_DEGREES
    assert shape.contains(-82.44 + 0.5 * step, 27.96 - 0.5 * step) is True
    assert shape.contains(-82.44 + 2 * step, 27.96 - 2 * step) is False
    assert shape.contains(0.0, 0.0) is False


def test_the_trip_buffer_constant_is_the_measured_one():
    """`GtfsMetadata.java:43-45`, and the value `tests/jtsoracle.py` fed the jar."""
    from jtsoracle import TRIP_BUFFER_DEGREES as ORACLE_DEGREES

    assert TRIP_BUFFER_METERS == 200
    assert TRIP_BUFFER_DEGREES == 0.001798640735523327
    assert TRIP_BUFFER_DEGREES == ORACLE_DEGREES
