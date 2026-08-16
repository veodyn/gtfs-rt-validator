"""`-ignoreShapes`: what it empties, what it leaves alone, and what it costs.

Upstream's flag skips exactly `GtfsMetadata.java:127-150`, the block the shapes
gate guards. Everything asserted here was measured against upstream at the pin,
and this module is where that measurement is now written down.

Two consequences reach output bytes, and both surface in the compat rules:

* **E029 is silently disabled.** `VehicleValidator` returns early on a `null`
  buffered trip shape, so the rule never fires and never says why.
* **E028's occurrence text changes.** `VehicleValidator.java:169-187` picks the
  shapes box when `getShapeBoundingBoxWithBuffer() != null` and the stops box
  otherwise, and the same branch sets `boundingDescription`, which lands in the
  message as `"...outside entire GTFS shapes.txt coverage area"` or
  `"...outside entire GTFS stops.txt coverage area"`. So the flag moves the
  geometry *and* the string. Both suffixes are pinned below so the rule module
  that eventually emits E028 inherits them rather than reinventing them.

The same fallback is what a feed with no `shapes.txt`, or with three or fewer
shape points, gets for free. `-ignoreShapes` is only the third way in. On the
count: the gate is `size() > 3`, so three is the closed case and four is open,
which prose descriptions of it routinely get backwards.
`tests/test_static_context_geometry.py` carries the correction and the evidence.

The CLI quirks belong to the flag surface in `gtfs_rt_validator.cli` and are
recorded here so they are not lost: upstream declares the option `.hasArg()`
but reads it with `hasOption`, so `-ignoreShapes false` **enables** it, and a
bare `-ignoreShapes` throws `MissingArgumentException` out of `main` rather
than being a no-op.
`-stats` has the identical shape.
"""

from __future__ import annotations

import tracemalloc

from gtfs_rt_validator.static.adapter import load_static
from gtfs_rt_validator.static.context import StaticContext
from gtfsfixtures import build_feed, minimal_tables
from test_static_context import context_from, stop_time, trip
from test_static_context_geometry import FOUR_POINTS, THREE_POINTS, shape_rows, two_shape_tables

# `VehicleValidator.java:186`, the tail of the E028 occurrence prefix. The only
# difference between them is the table name, and the flag chooses which one.
E028_SUFFIX_WITH_SHAPES = "outside entire GTFS shapes.txt coverage area"
E028_SUFFIX_WITHOUT_SHAPES = "outside entire GTFS stops.txt coverage area"

# 20,000 shape points: big enough that the shape rows dominate every other
# allocation by a factor of 50, small enough that the test costs the suite about
# 1.6 seconds, nearly all of it inside the sibling's loader. The docstring on
# the measurement test carries the numbers from a feed fifteen times this size.
MEASUREMENT_SHAPES = 20
MEASUREMENT_POINTS_PER_SHAPE = 1000


def e028_box_and_suffix(ctx: StaticContext):
    """`VehicleValidator.java:169-180`, the three lines E028 begins with.

    Transcribed here, and independently of the shipped code, because the string
    is an output-byte consequence of `-ignoreShapes` and this module is what
    pins the flag. `rules/_shared/vehicle_bounds.py:108` builds the same suffix
    for the rule that emits it.
    """
    if ctx.shape_bounding_box_buffered is not None:
        return ctx.shape_bounding_box_buffered, E028_SUFFIX_WITH_SHAPES
    return ctx.stop_bounding_box_buffered, E028_SUFFIX_WITHOUT_SHAPES


def test_ignore_shapes_empties_the_shape_block_and_keeps_the_stop_boxes(tmp_path):
    tables = two_shape_tables(FOUR_POINTS)

    ctx = context_from(tmp_path, tables, ignore_shapes=True)

    assert ctx.shape_points == {}
    assert ctx.trip_shapes == {}
    assert ctx.shape_bounding_box is None
    assert ctx.shape_bounding_box_buffered is None
    assert all(ctx.buffered_trip_shape(trip_id) is None for trip_id in ctx.trips)
    assert ctx.buffered_trip_shape("T1") is None, "the accessor, not just the loop"
    assert not ctx.stop_bounding_box.is_empty
    assert not ctx.stop_bounding_box_buffered.is_empty


def test_the_flag_is_honoured_by_the_context_and_not_only_by_the_adapter(tmp_path):
    """`load_static` skips the table; `StaticContext.build` skips the block.

    Two independent doors, and upstream only has the second one: its reader
    always loads `shapes.txt` and the flag is a constructor argument. Passing
    rows in with the flag set proves the context closes its own door, which is
    what keeps the two entry points honest if a caller ever loads shapes for one
    purpose and builds a context that ignores them for another.
    """
    path = build_feed(tmp_path, two_shape_tables(FOUR_POINTS))
    raw = load_static(path)

    assert len(raw.shapes) == 4, "the rows really were loaded, and they clear the gate"

    ctx = StaticContext.build(raw, ignore_shapes=True)

    assert ctx.shape_points == {}
    assert ctx.trip_shapes == {}
    assert ctx.shape_bounding_box_buffered is None


def test_everything_outside_the_shape_block_is_untouched(tmp_path):
    tables = two_shape_tables(FOUR_POINTS)
    with_shapes = context_from(tmp_path, tables)
    without = context_from(tmp_path, tables, ignore_shapes=True)

    assert without.timezone == with_shapes.timezone
    assert without.agency_ids == with_shapes.agency_ids
    assert without.stop_ids == with_shapes.stop_ids
    assert set(without.trips) == set(with_shapes.trips)
    assert set(without.trip_stop_times) == set(with_shapes.trip_stop_times)
    assert without.stop_location_types == with_shapes.stop_location_types
    assert without.stop_bounding_box == with_shapes.stop_bounding_box
    assert without.stop_bounding_box_buffered == with_shapes.stop_bounding_box_buffered


def test_e028_falls_back_to_the_stops_box_and_its_message_text_flips(tmp_path):
    """The output-byte difference, pinned before any rule can get it wrong."""
    tables = two_shape_tables(FOUR_POINTS)

    box, suffix = e028_box_and_suffix(context_from(tmp_path, tables))
    ignored_box, ignored_suffix = e028_box_and_suffix(
        context_from(tmp_path, tables, ignore_shapes=True)
    )

    assert suffix == "outside entire GTFS shapes.txt coverage area"
    assert ignored_suffix == "outside entire GTFS stops.txt coverage area"
    assert suffix != ignored_suffix
    assert box != ignored_box, "and the geometry moves too, not just the string"


def test_three_shape_points_take_the_same_fallback_without_the_flag(tmp_path):
    """The gate and the flag are indistinguishable downstream, which is the point."""
    gated = context_from(tmp_path, two_shape_tables(THREE_POINTS))
    flagged = context_from(tmp_path, two_shape_tables(FOUR_POINTS), ignore_shapes=True)

    assert e028_box_and_suffix(gated)[1] == E028_SUFFIX_WITHOUT_SHAPES
    assert e028_box_and_suffix(flagged)[1] == E028_SUFFIX_WITHOUT_SHAPES
    assert gated.shape_points == flagged.shape_points == {}


def test_the_three_empty_shape_states_are_told_apart_by_two_modern_members(tmp_path):
    """`shape_points` collapses all three, and that collapse is the parity.

    The test above says the gate and the flag are indistinguishable downstream,
    and for `GtfsMetadata`'s own members they are and must stay so. The modern
    question is a different one: "which shape ids does the static feed declare",
    which S016 and S044 ask and which has three different answers. `shape_ids`
    answers it where `shapes.txt` was read, and `shapes_withheld` says when it
    was not read at all and the question therefore has no answer.
    """
    flagged = context_from(tmp_path, two_shape_tables(FOUR_POINTS), ignore_shapes=True)
    gated = context_from(tmp_path, two_shape_tables(THREE_POINTS))
    without_the_table = minimal_tables()
    del without_the_table["shapes.txt"]
    absent = context_from(tmp_path, without_the_table)

    assert flagged.shape_points == gated.shape_points == absent.shape_points == {}
    assert (flagged.shapes_withheld, gated.shapes_withheld, absent.shapes_withheld) == (
        True,
        False,
        False,
    )
    assert flagged.shape_ids == frozenset(), "the loader never read the table"
    assert gated.shape_ids == frozenset({"SH1", "SH2"}), "read, then dropped by the gate"
    assert absent.shape_ids == frozenset(), "there is nothing to read, which is an answer"


def big_feed(tmp_path, shapes: int, points_per_shape: int):
    """A feed whose only bulk is `shapes.txt`, for the memory measurement."""
    tables = minimal_tables()
    tables["trips.txt"] = [dict(trip(f"T{s}"), shape_id=f"SH{s}") for s in range(shapes)]
    tables["stop_times.txt"] = [stop_time(f"T{s}", "S1", "1") for s in range(shapes)]
    tables["shapes.txt"] = shape_rows(
        [
            (f"SH{s}", seq + 1, 27.9 + seq * 0.0001, -82.5 + seq * 0.0001)
            for s in range(shapes)
            for seq in range(points_per_shape)
        ]
    )
    return build_feed(tmp_path, tables)


def peak_heap(path, *, ignore_shapes: bool) -> int:
    """Peak traced Python heap for one load-and-build, in bytes."""
    tracemalloc.start()
    try:
        StaticContext.build(
            load_static(path, ignore_shapes=ignore_shapes), ignore_shapes=ignore_shapes
        )
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_ignore_shapes_is_measured_rather_than_claimed(tmp_path):
    """A memory number rather than a claim. Here is the claim, tested.

    MEASURED 2026-08-14, macOS 15 on arm64, CPython 3.14, one process per
    reading, over `load_static` plus `StaticContext.build` on a feed of 300
    shapes of 1000 points: `shapes.txt` 9.2 MB uncompressed, every other table
    under 15 KB between them.

    | `-ignoreShapes` | peak traced heap | peak RSS | elapsed |
    |---|---|---|---|
    | off | 161.9 MB | 449 MB | 10.2 s |
    | on  |   1.1 MB |  30 MB |  0.0 s |

    So the flag is worth about 150x the traced heap and about 15x the resident
    set on that feed, and the resident figure is the one to quote: `tracemalloc`
    counts Python objects only, and the gap between 162 MB and 449 MB is the
    sibling's SQLite store and the interpreter itself. Both scale with the shape
    points and with nothing else, which is the whole reason upstream's own
    javadoc offers the flag as the answer to an `OutOfMemoryError`.

    This test re-measures a fifteenth of that feed so the suite stays quick, and
    asserts only the order of magnitude: 11.4 MB against 0.22 MB there, a factor
    of 53. The exact numbers move with the machine; the ratio does not.
    """
    path = big_feed(tmp_path, MEASUREMENT_SHAPES, MEASUREMENT_POINTS_PER_SHAPE)

    with_shapes = peak_heap(path, ignore_shapes=False)
    without = peak_heap(path, ignore_shapes=True)

    assert with_shapes > 10 * without, f"{with_shapes} bytes against {without} bytes"
