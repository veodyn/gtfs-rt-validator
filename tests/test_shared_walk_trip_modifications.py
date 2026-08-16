"""The TripModifications walk, read by eight spec-tier rules.

Three shapes, because the eight rules do not all ask the same question. S044,
S045, S049 and S050 read `selected_trips` and `service_dates`, which sit on the
`TripModifications` itself, so they need the owners including the ones carrying
no `Modification` at all. S041 is about a `Modification` that has no
`start_stop_selector`, so it needs the modifications including the ones carrying
no replacement stop. S046 and S047 are about one replacement stop each, so they
want the flat pairing. S048 is about `travel_time_to_stop` increasing *within* a
modification, so a flat stream that lost the grouping would let it compare the
last stop of one modification against the first of the next.
"""

from __future__ import annotations

from gtfs_rt_validator.rules._shared import walk_trip_modifications as walk
from gtfs_rt_validator.rules._shared.walk_trip_modifications import (
    modifications,
    replacement_stops,
    trip_modifications,
)
from specfixtures import context, entity, message, sharing


def modification(*stops, start=None):
    built: dict[str, object] = {"replacement_stops": [dict(stop) for stop in stops]}
    if start is not None:
        built["start_stop_selector"] = dict(start)
    return built


FIRST = entity(
    "first",
    trip_modifications={
        "selected_trips": [{"trip_ids": ["1.1"]}],
        "modifications": [
            modification(
                {"stop_id": "A", "travel_time_to_stop": 60},
                {"stop_id": "B", "travel_time_to_stop": 120},
                start={"stop_sequence": 3},
            ),
            modification(start={"stop_id": "C"}),
        ],
    },
)
SECOND = entity(
    "second",
    trip_modifications={
        "selected_trips": [{"trip_ids": ["2.1"]}],
        "modifications": [modification({"stop_id": "D", "travel_time_to_stop": 30})],
    },
)


#: A `TripModifications` carrying nothing but the two fields that live on the
#: owner. Four of the ten cohort H rules read only these.
BARE = entity(
    "bare",
    trip_modifications={
        "selected_trips": [{"trip_ids": ["3.1"], "shape_id": "S3"}],
        "service_dates": ["20260815"],
    },
)


def test_a_trip_modifications_carrying_no_modification_is_still_yielded():
    """S044, S045, S049 and S050 report against `selected_trips` and
    `service_dates`, which sit on the `TripModifications` and not on any
    `Modification`. A view derived from the modifications alone would make an
    entity that declares neither invisible to all four."""
    found = trip_modifications(message(BARE), context())

    assert [(record.entity_index, record.entity_id, record.path) for record in found] == [
        (0, "bare", "entity[0].trip_modifications")
    ]
    assert found[0].modifications == ()
    assert list(found[0].owner.get("service_dates")) == ["20260815"]


def test_the_owner_view_carries_the_modifications_that_belong_to_it():
    found = trip_modifications(message(FIRST, BARE, SECOND), context())

    assert [(record.entity_id, len(record.modifications)) for record in found] == [
        ("first", 2),
        ("bare", 0),
        ("second", 1),
    ]


def test_the_modification_view_is_the_owner_view_flattened():
    feed, ctx = message(FIRST, BARE, SECOND), context()

    assert modifications(feed, ctx) == tuple(
        record for owner in trip_modifications(feed, ctx) for record in owner.modifications
    )


def test_every_modification_is_yielded_with_its_indices_and_its_path():
    found = modifications(message(FIRST, SECOND), context())

    assert [(record.entity_index, record.index, record.path) for record in found] == [
        (0, 0, "entity[0].trip_modifications.modifications[0]"),
        (0, 1, "entity[0].trip_modifications.modifications[1]"),
        (1, 0, "entity[1].trip_modifications.modifications[0]"),
    ]


def test_a_modification_with_no_replacement_stop_is_still_yielded():
    """S041's own predicate is about the modification, so a walk that only
    yielded replacement stops would leave it unable to see the modification that
    has none."""
    found = modifications(message(FIRST), context())

    assert [len(record.replacement_stops) for record in found] == [2, 0]
    assert found[1].modification.get("start_stop_selector").get("stop_id") == "C"


def test_the_replacement_stops_keep_their_index_and_their_path():
    found = modifications(message(FIRST), context())

    assert [(stop.index, stop.path) for stop in found[0].replacement_stops] == [
        (0, "entity[0].trip_modifications.modifications[0].replacement_stops[0]"),
        (1, "entity[0].trip_modifications.modifications[0].replacement_stops[1]"),
    ]


def test_the_flat_view_pairs_each_stop_with_the_modification_it_came_from():
    """S046 and S047 report against one replacement stop and locate it by the
    modification's path, which the stop alone cannot say."""
    found = replacement_stops(message(FIRST, SECOND), context())

    assert [(record.index, stop.stop.get("stop_id")) for record, stop in found] == [
        (0, "A"),
        (0, "B"),
        (0, "D"),
    ]


def test_the_grouping_survives_so_s048_never_compares_across_modifications():
    """`travel_time_to_stop` is monotonic within a modification. Flattened
    without the grouping, B at 120 followed by D at 30 reads as a decrease that
    the clause says nothing about."""
    found = modifications(message(FIRST, SECOND), context())

    assert [
        [stop.stop.get("travel_time_to_stop") for stop in record.replacement_stops]
        for record in found
    ] == [[60, 120], [], [30]]


def test_an_entity_carrying_no_trip_modifications_contributes_nothing():
    """`getTripModifications()` on an entity that names none answers a default
    instance with an empty modification list, so this is about the walk testing
    presence rather than about the count coming out right by accident."""
    assert modifications(message(entity("a"), entity("b", vehicle={})), context()) == ()


def test_eight_rules_sharing_one_context_walk_the_modifications_once(monkeypatch):
    """S041 and S044 to S050 read one message between them."""
    runs = sharing(monkeypatch, walk, "_build")
    feed = message(FIRST, SECOND)
    ctx = context()

    assert len(trip_modifications(feed, ctx)) == 2
    assert len(modifications(feed, ctx)) == 3
    assert len(list(replacement_stops(feed, ctx))) == 3
    assert [record.index for record in modifications(feed, ctx)] == [0, 1, 0]
    assert [stop.index for _, stop in replacement_stops(feed, ctx)] == [0, 1, 0]

    assert runs == [feed]
