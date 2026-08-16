"""S044, its `-ignoreShapes` gate, and the specific mistake its clause warns of.

The clause is not "a shape_id must resolve". It is a warning against one
substitution: writing the `FeedEntity.id` where the `shape_id` *inside* the
entity was meant. A rule that reported only "unresolvable" would throw away the
finding its own citation exists for, so the occurrence says when the value is a
`FeedEntity.id` of this message.

The gate is the bug that made E029 silently vanish under `-ignoreShapes`, in a
new place: with the flag set `shapes.txt` is never read, and a rule that
reported from that state would call every `shape_id` in the feed unresolvable.
It is only that state. An archive with no `shapes.txt` and an archive whose
`shapes.txt` falls below `GtfsMetadata.java:127`'s four-point gate both empty
`shape_points` too, and in neither is anything unknown: the first declares no
shape ids and the second declares its own. So the early return is
`ctx.static.shapes_withheld` and the resolution reads `ctx.static.shape_ids`,
which is the ungated id column. The three states are the three tests below.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.spec.s044 import check
from tripmodfixtures import entity, message, minimal, paths, prefixes, rule_context
from tripmodfixtures import trip_modifications as tm

#: Three points feed-wide: below the compat gate, and still a declared `SH1`.
SHORT_SHAPE_ROWS = [
    {
        "shape_id": "SH1",
        "shape_pt_lat": "27.95",
        "shape_pt_lon": "-82.45",
        "shape_pt_sequence": str(sequence),
    }
    for sequence in (1, 2, 3)
]

UNRESOLVED = "shape_id {} is in neither shapes.txt nor a Shape entity of this feed"
CONFUSED = ", and is the id of a FeedEntity rather than the shape_id inside one"


def test_a_shape_id_in_shapes_txt_resolves(tmp_path: Path):
    feed = message(tm(trip_ids=["T1"], shape_id="SH1"))

    assert prefixes(check(feed, rule_context(tmp_path))) == []


def test_a_shape_id_in_neither_place_is_reported(tmp_path: Path):
    ctx = rule_context(tmp_path)
    feed = message(tm(trip_ids=["T1"], shape_id="NOPE"))

    assert prefixes(check(feed, ctx)) == [UNRESOLVED.format("NOPE")]
    assert paths(check(feed, ctx)) == ["entity[0].trip_modifications.selected_trips[0]"]


def test_a_shape_defined_by_a_shape_entity_of_the_same_feed_resolves(tmp_path: Path):
    feed = message(
        entity("sh", shape={"shape_id": "RT1", "encoded_polyline": "_p~iF~ps|U"}),
        tm(trip_ids=["T1"], shape_id="RT1"),
    )

    assert prefixes(check(feed, rule_context(tmp_path))) == []


def test_the_feed_entity_id_written_instead_of_the_shape_id_is_named_as_such(tmp_path: Path):
    """What `1202#1` was written to prevent, reported as itself."""
    feed = message(
        entity("sh", shape={"shape_id": "RT1", "encoded_polyline": "_p~iF~ps|U"}),
        tm(trip_ids=["T1"], shape_id="sh"),
    )

    assert prefixes(check(feed, rule_context(tmp_path))) == [UNRESOLVED.format("sh") + CONFUSED]


def test_nothing_is_reported_when_shapes_were_withheld(tmp_path: Path):
    """`-ignoreShapes` skips `shapes.txt` entirely, so the ids of a feed whose
    shapes are perfectly good were never read. Reporting from that state is how
    E029 came to vanish silently under the same flag, in reverse."""
    feed = message(tm(trip_ids=["T1"], shape_id="NOPE"))

    assert prefixes(check(feed, rule_context(tmp_path, ignore_shapes=True))) == []


def test_an_archive_with_no_shapes_txt_is_reported_rather_than_skipped(tmp_path: Path):
    """The table is optional. Without it no static shape id exists, so "this is
    not one" is decidable and the entity-id substitution, which is the whole of
    the cited sentence, needs no `shapes.txt` in the first place."""
    tables = minimal()
    del tables["shapes.txt"]
    ctx = rule_context(tmp_path, tables)
    feed = message(
        entity("sh", shape={"shape_id": "RT1", "encoded_polyline": "_p~iF~ps|U"}),
        tm(trip_ids=["T1"], shape_id="sh"),
    )

    assert prefixes(check(feed, ctx)) == [UNRESOLVED.format("sh") + CONFUSED]
    assert prefixes(check(message(tm(trip_ids=["T1"], shape_id="NOPE")), ctx)) == [
        UNRESOLVED.format("NOPE")
    ]


def test_a_shapes_txt_below_the_point_gate_still_defines_its_ids(tmp_path: Path):
    """`GtfsMetadata.java:127` empties `shape_points` at three points feed-wide,
    which is compat parity and does not move. `SH1` is still a shape the feed
    declares, and `NOPE` is still not one."""
    tables = minimal()
    tables["shapes.txt"] = SHORT_SHAPE_ROWS
    ctx = rule_context(tmp_path, tables)

    assert prefixes(check(message(tm(trip_ids=["T1"], shape_id="SH1")), ctx)) == []
    assert prefixes(check(message(tm(trip_ids=["T1"], shape_id="NOPE")), ctx)) == [
        UNRESOLVED.format("NOPE")
    ]


def test_a_selected_trips_with_no_shape_id_is_not_reported(tmp_path: Path):
    feed = message(tm(trip_ids=["T1"]))

    assert prefixes(check(feed, rule_context(tmp_path))) == []


def test_every_selected_trips_of_every_entity_is_read(tmp_path: Path):
    """`selected_trips` is repeated, and it lives on the `TripModifications`
    rather than on a `Modification`, so a walk that started from the
    modifications would see none of this."""
    feed = message(
        tm(trip_ids=["T1"], shape_id="X", entity_id="one"),
        tm(trip_ids=["T2"], shape_id="Y", entity_id="two"),
    )

    assert paths(check(feed, rule_context(tmp_path))) == [
        "entity[0].trip_modifications.selected_trips[0]",
        "entity[1].trip_modifications.selected_trips[0]",
    ]
