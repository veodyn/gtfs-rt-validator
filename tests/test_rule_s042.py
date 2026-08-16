"""S042, and the two sites a `StopSelector` can appear at in the pinned proto.

Measured rather than assumed:

    [(m, f.name) for m in SCHEMA.messages
     for f in SCHEMA.message(m).fields if f.type_name == "StopSelector"]

answers `TripModifications.Modification.start_stop_selector` and
`.end_stop_selector` and nothing else, so those two are the whole surface. The
rule walks both, and a site added at a later pin is a clause-index failure rather
than a silent gap.

E040 is the same shape ("one of the fields below must necessarily be set") on
`StopTimeUpdate`, which is a different message this rule never reaches. The jar
cannot refute the boundary either way: `StopSelector` postdates it.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s042 import check
from tripmodfixtures import context, message, modification, paths, prefixes
from tripmodfixtures import trip_modifications as tm


def test_the_two_sites_this_rule_walks_are_the_only_ones_the_pin_declares():
    found = [
        f"{name}.{field.name}"
        for name in SCHEMA.messages
        for field in SCHEMA.message(name).fields
        if field.type_name == "StopSelector"
    ]

    assert found == [
        "TripModifications.Modification.start_stop_selector",
        "TripModifications.Modification.end_stop_selector",
    ]


def test_a_start_stop_selector_with_neither_value_is_reported():
    feed = message(tm(modification(start={})))

    assert prefixes(check(feed, context())) == [
        "start_stop_selector with neither stop_sequence nor stop_id"
    ]
    assert paths(check(feed, context())) == [
        "entity[0].trip_modifications.modifications[0].start_stop_selector"
    ]


def test_an_end_stop_selector_with_neither_value_is_reported():
    feed = message(tm(modification(start={"stop_id": "A"}, end={})))

    assert prefixes(check(feed, context())) == [
        "end_stop_selector with neither stop_sequence nor stop_id"
    ]


def test_either_value_alone_satisfies_the_clause():
    feed = message(
        tm(modification(start={"stop_sequence": 0}, end={"stop_id": "B"}), entity_id="one"),
        tm(modification(start={"stop_id": "A"}), entity_id="two"),
    )

    assert prefixes(check(feed, context())) == []


def test_an_absent_selector_is_not_a_selector_with_neither_value():
    """S041 owns the absent `start_stop_selector`, at its own clause. An absent
    `end_stop_selector` is what `:1168` describes and no rule checks, because
    the antecedent there is defined by the field's own absence."""
    feed = message(tm(modification()))

    assert prefixes(check(feed, context())) == []


def test_both_selectors_of_one_modification_report_separately():
    feed = message(tm(modification(start={}, end={})))

    assert paths(check(feed, context())) == [
        "entity[0].trip_modifications.modifications[0].start_stop_selector",
        "entity[0].trip_modifications.modifications[0].end_stop_selector",
    ]
