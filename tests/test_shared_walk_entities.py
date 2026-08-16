"""The entity-level walk, read by S001, S002 and S003.

Three claims, and the third is the one no output test would catch:

- the payload names come from the `FeedEntity` descriptor rather than a list,
  so the walk sees the six payloads the current schema declares and would see a
  seventh the day one is added;
- an entity carrying none of them, and an entity carrying two, are both
  describable, which is what S001 needs and what a bare `payload_kind` could
  not express;
- three rules reading it in one context walk the entities once.
"""

from __future__ import annotations

from gtfs_rt_validator.proto import schema_2015, schema_current
from gtfs_rt_validator.rules._shared import walk_entities
from gtfs_rt_validator.rules._shared.walk_entities import entities, payload_names
from specfixtures import context, entity, message, sharing

TRIP = {"trip": {"trip_id": "1.1"}}
SHAPE = {"shape_id": "S1", "encoded_polyline": "_p~iF~ps|U"}


def test_the_payload_names_come_from_the_descriptor_not_from_a_list():
    """The six `FeedEntity` payloads, in field-number order. A hand-written list
    would be a place the pin has to be remembered, and the walk would go on
    reporting a seventh payload as no payload at all."""
    assert payload_names(schema_current.SCHEMA.message("FeedEntity")) == (
        "trip_update",
        "vehicle",
        "alert",
        "shape",
        "stop",
        "trip_modifications",
    )


def test_the_same_walk_over_the_2015_entity_sees_the_three_payloads_it_has():
    """The descriptor answers for whichever schema decoded the message, which is
    what makes this a walk rather than a second copy of the current schema."""
    assert payload_names(schema_2015.SCHEMA.message("FeedEntity")) == (
        "trip_update",
        "vehicle",
        "alert",
    )


def test_every_entity_is_yielded_with_its_index_its_payload_and_its_path():
    found = entities(
        message(
            entity("a", trip_update=TRIP),
            entity("b", shape=SHAPE),
            entity("c", trip_modifications={}),
        ),
        context(),
    )

    assert [(record.index, record.entity_id, record.payload) for record in found.records] == [
        (0, "a", "trip_update"),
        (1, "b", "shape"),
        (2, "c", "trip_modifications"),
    ]
    assert [record.path for record in found.records] == ["entity[0]", "entity[1]", "entity[2]"]


def test_an_entity_with_no_payload_and_one_with_two_are_both_describable():
    """S001's own predicate. `payload` is `None` for both, and `payloads` is
    what says which of the two it was, so the rule reports the right one."""
    found = entities(message(entity("none"), entity("two", trip_update=TRIP, alert={})), context())

    assert [record.payloads for record in found.records] == [(), ("trip_update", "alert")]
    assert [record.payload for record in found.records] == [None, None]


def test_a_deleted_entity_is_flagged_rather_than_dropped():
    """S001 exempts a deleted entity from needing a payload, so the walk has to
    hand the rule the flag rather than decide for it."""
    found = entities(message(entity("gone", is_deleted=True), entity("here")), context())

    assert [record.is_deleted for record in found.records] == [True, False]


def test_the_id_multiset_counts_every_entity_and_names_the_repeats():
    """S002 is about `id` uniqueness within one FeedMessage, so what it needs is
    the count, not the set."""
    found = entities(
        message(entity("a", trip_update=TRIP), entity("b"), entity("a"), entity("b"), entity("c")),
        context(),
    )

    assert dict(found.id_counts) == {"a": 2, "b": 2, "c": 1}
    assert found.repeated_ids() == ("a", "b")


def test_the_records_can_be_filtered_by_payload():
    """S003 reads the TripUpdate entities and nothing else, and filtering the
    one walk is what keeps it from writing a second one."""
    found = entities(
        message(entity("a", trip_update=TRIP), entity("b", shape=SHAPE), entity("c", vehicle={})),
        context(),
    )

    assert [record.entity_id for record in found.carrying("trip_update")] == ["a"]
    assert [record.entity_id for record in found.carrying("shape")] == ["b"]


def test_three_rules_sharing_one_context_walk_the_entities_once(monkeypatch):
    """The whole point of the memo. S001, S002 and S003 read one message; a walk
    that reran per rule would report exactly the same thing and cost three
    passes, which no assertion about output could ever notice."""
    runs = sharing(monkeypatch, walk_entities, "_build")
    feed = message(entity("a", trip_update=TRIP), entity("b", shape=SHAPE))
    ctx = context()

    assert len(entities(feed, ctx).records) == 2
    assert entities(feed, ctx).repeated_ids() == ()
    assert [record.entity_id for record in entities(feed, ctx).carrying("shape")] == ["b"]

    assert runs == [feed]


def test_a_second_message_is_walked_again():
    """The memo dies with the message, so nothing carries across a cycle."""
    first, second = message(entity("a")), message(entity("b"))
    ctx = context()

    assert [record.entity_id for record in entities(first, ctx).records] == ["a"]
    assert [record.entity_id for record in entities(second, context()).records] == ["b"]
