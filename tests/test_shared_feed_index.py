"""The whole-message index, read by S016, S020, S043, S044, S045, S046 and S047.

The correctness trap is the reason this exists at all, and it is the first test
below: `FeedEntity` ordering is not specified, so a `TripModifications` entity
may precede the `Shape` entity it names. An index built as the walk went would
report a correct feed as broken depending on the order its entities happen to be
written in, and the fixture that caught it would have to be the one with the
unlucky order. Reversing the entities is what makes that not a matter of luck.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules._shared import feed_index
from gtfs_rt_validator.rules._shared.feed_index import index
from specfixtures import context, entity, message, sharing

REPLACEMENT = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]["REPLACEMENT"]
DUPLICATED = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]["DUPLICATED"]

SHAPE = entity("shape-entity", shape={"shape_id": "S1", "encoded_polyline": "_p~iF~ps|U_ulL"})
STOP = entity("stop-entity", stop={"stop_id": "NEW-1"})
MODIFICATIONS = entity(
    "modifications-entity",
    trip_modifications={
        "selected_trips": [{"trip_ids": ["1.1"], "shape_id": "S1"}],
        "service_dates": ["20260814"],
        "modifications": [{"start_stop_selector": {"stop_id": "NEW-1"}}],
    },
)
REPLACED = entity(
    "replaced-entity",
    trip_update={"trip": {"trip_id": "1.1", "schedule_relationship": REPLACEMENT}},
)
DUPLICATE = entity(
    "duplicate-entity",
    trip_update={
        "trip": {"trip_id": "1.1", "schedule_relationship": DUPLICATED},
        "trip_properties": {"trip_id": "1.1-copy", "start_date": "20260814"},
    },
)

ALL = (SHAPE, STOP, MODIFICATIONS, REPLACED, DUPLICATE)


def summary(built) -> dict[str, object]:
    """Every key set the index answers, in a shape two builds can be compared on.

    The values are decoded messages, which compare by identity, so two builds
    over two encodings of the same feed can only be compared on their keys. The
    keys are what the seven rules ask about.
    """
    return {
        "entity_ids": built.entity_ids,
        "shapes": sorted(built.shapes),
        "stops": sorted(built.stops),
        "trip_property_trip_ids": built.trip_property_trip_ids,
        "replacement_trip_updates": sorted(built.replacement_trip_updates),
    }


def test_reversing_the_entity_order_changes_nothing():
    """The whole contract. It is an index, so the order the feed was written in
    is not allowed to reach any answer it gives."""
    forward = index(message(*ALL), context())
    backward = index(message(*reversed(ALL)), context())

    assert summary(forward) == summary(backward)


def test_a_reference_that_precedes_its_definition_still_resolves():
    """The concrete shape of the same trap: S044 asks whether a `SelectedTrips`
    shape_id resolves, and the `Shape` entity defining it is written after the
    `TripModifications` entity that names it."""
    built = index(message(MODIFICATIONS, SHAPE, STOP), context())

    assert built.defines_shape("S1")
    assert built.defines_stop("NEW-1")


def test_the_index_answers_no_for_an_id_the_feed_never_defines():
    """The negative direction, which is the one that ships if it is skipped: an
    index that answered yes to everything would pass every positive test above
    and silence S016, S043, S044 and S046 completely."""
    built = index(message(*ALL), context())

    assert not built.defines_shape("S2")
    assert not built.defines_stop("A")


def test_the_entity_ids_are_indexed_because_s016_reports_the_confusion_by_name():
    """`:414` warns against writing the `FeedEntity.id` where a `shape_id` was
    meant, so S016 reports that specific mistake when it can, and needs the
    entity ids to recognise it."""
    built = index(message(*ALL), context())

    assert built.entity_ids == frozenset(
        {
            "shape-entity",
            "stop-entity",
            "modifications-entity",
            "replaced-entity",
            "duplicate-entity",
        }
    )


def test_only_replacement_trip_updates_are_indexed_as_replacements():
    """S045 fires when a `TripUpdate` with `schedule_relationship=REPLACEMENT`
    already exists for a selected trip. An index that carried every TripUpdate
    would make it fire on every modified trip in the feed."""
    built = index(message(*ALL), context())

    assert sorted(built.replacement_trip_updates) == ["1.1"]


def test_the_trip_properties_trip_ids_are_indexed_for_s020():
    """S020 pairs a DUPLICATED VehiclePosition against
    `TripUpdate.TripProperties.trip_id`, which is a different field from the
    descriptor's own trip_id and is why this is not E047."""
    built = index(message(*ALL), context())

    assert built.trip_property_trip_ids == frozenset({"1.1-copy"})


def test_an_entity_that_defines_nothing_is_not_indexed_under_the_empty_string():
    """`Shape.shape_id` and `Stop.stop_id` are both optional, and a `Shape`
    without one is S037's finding. Indexing it under `""` would make every
    other rule's lookup of an empty id succeed."""
    built = index(
        message(entity("a", shape={"encoded_polyline": "_p~iF"}), entity("b", stop={})), context()
    )

    assert not built.defines_shape("")
    assert not built.defines_stop("")


def test_seven_rules_sharing_one_context_build_the_index_once(monkeypatch):
    """The module that would otherwise be copy-pasted seven times is also the
    one that would otherwise be rebuilt seven times."""
    runs = sharing(monkeypatch, feed_index, "_build")
    feed = message(*ALL)
    ctx = context()

    for _ in range(7):
        assert index(feed, ctx).defines_shape("S1")

    assert runs == [feed]


def test_a_second_message_in_one_context_needs_a_scope_of_its_own(monkeypatch):
    """S020 reads a VehiclePosition against the TripUpdates of the same cycle,
    which is a second message in one context. Without a scope it would be handed
    this message's index and would resolve every id against the wrong feed."""
    runs = sharing(monkeypatch, feed_index, "_build")
    host, other = message(*ALL), message(SHAPE)
    ctx = context()

    assert index(host, ctx).trip_property_trip_ids == frozenset({"1.1-copy"})
    assert index(other, ctx, scope="vp").trip_property_trip_ids == frozenset()

    assert runs == [host, other]
