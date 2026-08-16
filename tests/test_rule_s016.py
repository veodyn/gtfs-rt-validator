"""S016: a `TripProperties.shape_id` that resolves to nothing.

**The `-ignoreShapes` early return is the first test here on purpose**, because
every later shape rule copies its shape, and the three tests after it are the
three states that early return used to cover and no longer does. Reporting from
a `shape_points` that `-ignoreShapes` emptied would be the bug that makes E029
vanish silently under the same flag, in reverse. But `shape_points` is empty for
two further reasons that are not that bug: an archive with no `shapes.txt`,
where no static shape id exists and so no value can be one, and
`GtfsMetadata`'s four-point gate, where `shapes.txt` was read and declares its
ids whatever the geometry did. The rule now returns early on
`ctx.static.shapes_withheld` and resolves against `ctx.static.shape_ids`.

The clause S016 cites is about the *specific* mistake of writing the
`FeedEntity.id` where the `shape_id` inside the entity was meant, so the rule
says which of the two it found. That is what `feed_index.entity_ids` is for.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.spec.s016 import check
from specfixtures import entity, feed_context, message, minimal, prefixes

SHAPE_ROWS = [
    {
        "shape_id": "RT-SHAPE",
        "shape_pt_lat": "27.95",
        "shape_pt_lon": "-82.45",
        "shape_pt_sequence": str(sequence),
    }
    for sequence in (1, 2)
]

#: Three points feed-wide, which is `GtfsMetadata.java:127`'s closed case: the
#: shape is declared, and `shape_points` will be empty anyway.
SHORT_SHAPE_ROWS = [
    {
        "shape_id": "SH1",
        "shape_pt_lat": "27.95",
        "shape_pt_lon": "-82.45",
        "shape_pt_sequence": str(sequence),
    }
    for sequence in (1, 2, 3)
]


def trip_update(shape_id: str | None = None, trip_id: str = "T1") -> dict[str, object]:
    """A TripUpdate whose `trip_properties` names this shape_id, or none at all."""
    properties: dict[str, object] = {} if shape_id is None else {"shape_id": shape_id}
    return {"trip": {"trip_id": trip_id}, "trip_properties": properties}


def shape_entity(shape_id: str, entity_id: str = "shape-entity") -> dict[str, object]:
    return entity(entity_id, shape={"shape_id": shape_id, "encoded_polyline": "_p~iF~ps|U_ulL"})


def run(tmp_path, *entities, tables=None, ignore_shapes: bool = False):
    ctx = feed_context(tmp_path, tables, ignore_shapes=ignore_shapes)
    return check(message(*entities), ctx)


# --- the gate, first ---------------------------------------------------------


def test_no_shapes_were_loaded_so_the_rule_says_nothing(tmp_path):
    """`-ignoreShapes`, and the only state that still silences this rule.

    The table is never read, so this project cannot know whether `SH1` is a
    shape `shapes.txt` declares. Every answer it could give would be a guess."""
    found = run(tmp_path, entity(trip_update=trip_update("SH1")), ignore_shapes=True)

    assert found is None


def test_an_archive_with_no_shapes_txt_is_not_the_same_gate(tmp_path):
    """The table is optional, so an archive without it loads clean, and then
    "no shape id in this feed is a static one" is true rather than unknown.
    Silence here was the audit's finding: the gate covered a state its own
    reason does not reach."""
    tables = minimal()
    del tables["shapes.txt"]
    found = run(tmp_path, entity(trip_update=trip_update("SH1")), tables=tables)

    assert prefixes(found) == [
        "trip_id T1 shape_id SH1 is in neither shapes.txt nor a Shape entity of this feed"
    ]


def test_an_archive_with_no_shapes_txt_still_names_the_entity_id_mistake(tmp_path):
    """The half of the rule its own `source=` sentence is entirely about. It
    needs the realtime entity index and no static shapes at all."""
    tables = minimal()
    del tables["shapes.txt"]
    found = run(
        tmp_path,
        entity(trip_update=trip_update("shape-entity")),
        shape_entity("RT-SHAPE", entity_id="shape-entity"),
        tables=tables,
    )

    assert prefixes(found) == [
        "trip_id T1 shape_id shape-entity is a FeedEntity id, not the shape_id inside it"
    ]


def test_a_shapes_txt_below_the_point_gate_still_defines_its_ids(tmp_path):
    """`GtfsMetadata.java:127` empties `shape_points` for a feed of three shape
    points or fewer, and that gate is compat parity and does not move. It is the
    wrong structure to ask which ids exist, which is why `shape_ids` does."""
    tables = minimal()
    tables["shapes.txt"] = SHORT_SHAPE_ROWS
    found = run(tmp_path, entity(trip_update=trip_update("SH1")), tables=tables)

    assert prefixes(found) == [], "three points is still a shape SH1"

    missing = run(tmp_path, entity(trip_update=trip_update("NOPE")), tables=tables)

    assert prefixes(missing) == [
        "trip_id T1 shape_id NOPE is in neither shapes.txt nor a Shape entity of this feed"
    ]


def test_a_real_time_shape_still_does_not_reopen_the_gate(tmp_path):
    """The gate is about whether `shapes.txt` was read. A feed defining its own
    `Shape` entity under `-ignoreShapes` is still not checked, because the
    static half of the resolution cannot be asked."""
    found = run(
        tmp_path,
        entity(trip_update=trip_update("RT-SHAPE")),
        shape_entity("RT-SHAPE"),
        ignore_shapes=True,
    )

    assert found is None


# --- resolution --------------------------------------------------------------


def test_a_shape_id_from_shapes_txt_resolves(tmp_path):
    """`SH1` is `minimal_tables()`'s own shape, over four points."""
    found = run(tmp_path, entity(trip_update=trip_update("SH1")))

    assert prefixes(found) == []


def test_a_shape_id_defined_by_a_shape_entity_of_the_same_feed_resolves(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update("RT-SHAPE")), shape_entity("RT-SHAPE"))

    assert prefixes(found) == []


def test_the_shape_entity_may_be_written_after_the_trip_update(tmp_path):
    """`feed_index` is built from the whole message, so entity order cannot
    decide whether a correct feed is reported."""
    found = run(tmp_path, shape_entity("RT-SHAPE"), entity(trip_update=trip_update("RT-SHAPE")))

    assert prefixes(found) == []


def test_a_shape_id_that_resolves_nowhere_is_reported(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update("NOPE")))

    assert prefixes(found) == [
        "trip_id T1 shape_id NOPE is in neither shapes.txt nor a Shape entity of this feed"
    ]


def test_the_feed_entity_id_written_instead_of_the_shape_id_is_named_as_such(tmp_path):
    """The mistake the clause was written to prevent, so a bare `unresolvable`
    would waste it."""
    found = run(
        tmp_path,
        entity(trip_update=trip_update("shape-entity")),
        shape_entity("RT-SHAPE", entity_id="shape-entity"),
    )

    assert prefixes(found) == [
        "trip_id T1 shape_id shape-entity is a FeedEntity id, not the shape_id inside it"
    ]


def test_a_trip_update_with_no_trip_properties_is_not_a_finding(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update()))

    assert prefixes(found) == []


def test_a_shape_entity_of_its_own_is_not_a_finding(tmp_path):
    """S037 and S038 are the rules about a `Shape` entity. This one only reads
    `TripProperties`."""
    found = run(tmp_path, shape_entity("RT-SHAPE"))

    assert prefixes(found) == []


def test_every_offending_trip_update_reports_once_in_entity_order(tmp_path):
    found = run(
        tmp_path,
        entity("one", trip_update=trip_update("X1", trip_id="A")),
        entity("two", trip_update=trip_update("X2", trip_id="B")),
    )

    assert [occurrence.rule_id for occurrence in found] == ["S016", "S016"]
    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.trip_properties",
        "entity[1].trip_update.trip_properties",
    ]


def test_the_rule_reads_shapes_txt_rather_than_the_trips_that_use_it(tmp_path):
    """A `shape_id` that `shapes.txt` defines but no trip in `trips.txt` uses
    still resolves: the clause is about the id being defined, not about which
    trip it belongs to."""
    tables = minimal(shapes=SHAPE_ROWS)
    found = run(tmp_path, entity(trip_update=trip_update("RT-SHAPE")), tables=tables)

    assert prefixes(found) == []
