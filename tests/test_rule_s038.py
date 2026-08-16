"""S038: a realtime `Shape` reusing a shape_id the static feed already defines.

The fixture feed defines `SH1` over four shape points, which is what gets it
past `GtfsMetadata`'s feed-wide `shapePoints.size() > 3` gate. The last test
below pins what happens under `-ignoreShapes`, where the gate is shut and this
rule can only under-report; that direction is stated rather than worked around,
because nothing in a run can tell a shut gate from a feed with no shapes.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s038 import check
from gtfsfixtures import minimal_tables
from rulefixtures import static_context
from specfixtures import context, entity, message

LINE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
COLLIDES = "entity ID s0 shape_id SH1 is already defined in the GTFS shapes.txt"


def found(tmp_path: Path, *shape_ids, ignore_shapes: bool = False):
    feed = message(
        *(
            entity(f"s{index}", shape={"shape_id": each, "encoded_polyline": LINE})
            for index, each in enumerate(shape_ids)
        )
    )
    ctx = context(static=static_context(tmp_path, ignore_shapes=ignore_shapes))
    return list(check(feed, ctx) or ())


def prefixes(tmp_path: Path, *shape_ids, ignore_shapes: bool = False):
    return [o.prefix for o in found(tmp_path, *shape_ids, ignore_shapes=ignore_shapes)]


def test_the_fixture_feed_really_defines_the_static_shape(tmp_path: Path):
    """Four shape points, which is what clears the feed-wide gate. A feed below
    it loads no shapes at all and would make every test here vacuous."""
    assert set(static_context(tmp_path).shape_points) == {"SH1"}


def test_a_shape_id_that_the_static_feed_defines_reports(tmp_path: Path):
    assert prefixes(tmp_path, "SH1") == [COLLIDES]


def test_a_three_point_shape_is_still_a_shape_the_static_feed_defines(tmp_path: Path):
    """`_tables.SHAPE_POINT_GATE` reproduces `GtfsMetadata.java:127`'s feed-wide
    `shapePoints.size() > 3`, so a feed of three points or fewer loads no
    geometry at all. That is a compat contract and it stays exactly as it is.
    It is simply the wrong structure to ask which ids `shapes.txt` declares:
    three ordered points are a valid shape, and the collision the clause forbids
    is a collision of ids and not of polylines. `shape_ids` is the ungated
    source, read straight off the table before the gate sees it."""
    tables = minimal_tables()
    tables["shapes.txt"] = tables["shapes.txt"][:3]
    ctx = context(static=static_context(tmp_path, tables))
    feed = message(entity("s0", shape={"shape_id": "SH1", "encoded_polyline": LINE}))

    assert ctx.static.shape_points == {}
    assert ctx.static.shape_ids == frozenset({"SH1"})
    assert [found.prefix for found in (check(feed, ctx) or ())] == [COLLIDES]


def test_a_shape_id_of_its_own_is_silent(tmp_path: Path):
    """The satisfying fixture, and the shape the clause is written to produce:
    a detour needs an id nothing in the static feed claims."""
    assert prefixes(tmp_path, "RT1") == []


def test_the_occurrence_locates_the_shape(tmp_path: Path):
    (occurrence,) = found(tmp_path, "RT1", "SH1")

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[1].shape"


def test_a_shape_with_no_shape_id_is_out_of_scope(tmp_path: Path):
    """S037's finding. There is no value here to be different from anything."""
    feed = message(entity("s0", shape={"encoded_polyline": LINE}))

    assert list(check(feed, context(static=static_context(tmp_path))) or ()) == []


def test_each_colliding_shape_reports_once(tmp_path: Path):
    assert len(prefixes(tmp_path, "SH1", "RT1", "SH1")) == 2


def test_ignore_shapes_can_only_under_report(tmp_path: Path):
    """Under `-ignoreShapes` the static feed holds no shape at all, so nothing
    collides and this rule goes quiet. That is a false negative and never a
    false positive, which is why there is no early return: the rule that needed
    one is S016, where an empty table would make every reference unresolvable.

    This survives the move to `shape_ids` because the flag empties
    `RawTables.shapes` at the loader (`adapter._requested`) rather than at the
    gate, so there is nothing left to read before the gate either. The point
    gate alone no longer silences this rule, which is what the three-point test
    above pins."""
    assert prefixes(tmp_path, "SH1", ignore_shapes=True) == []
