"""S041, against the clause and against the shape of a feed that satisfies it.

`1165#1` is one of the few sentences in the pinned proto that says outright that
an `optional` field is required. `Modification.start_stop_selector` is declared
optional for the reason `Shape.shape_id` is (proto2's "Required is Forever"), and
the comment is the normative source: a validator that read the wire cardinality
as the spec would enforce the opposite of what the file says.

**No jar oracle, and not even a negative one.** `TripModifications` postdates the
jar entirely, so the message decodes to nothing there and the differential can
neither confirm this rule nor refute the claim that it borders nothing
upstream. The satisfying fixture
below is doing the work the jar does for the 56: with no oracle, over-firing is
the failure that ships.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.spec.s041 import check
from tripmodfixtures import context, entity, message, modification, paths, prefixes
from tripmodfixtures import trip_modifications as tm


def test_a_modification_with_no_start_stop_selector_is_reported():
    feed = message(tm(modification({"stop_id": "A"})))

    assert prefixes(check(feed, context())) == ["a Modification with no start_stop_selector"]
    assert paths(check(feed, context())) == ["entity[0].trip_modifications.modifications[0]"]


def test_a_modification_that_declares_one_is_not_reported():
    feed = message(tm(modification({"stop_id": "A"}, start={"stop_sequence": 3})))

    assert prefixes(check(feed, context())) == []


def test_an_empty_start_stop_selector_still_counts_as_declared():
    """Presence, not content. A `StopSelector` carrying neither of its two
    fields is S042's finding and reporting it here as well would double-count
    one mistake against two clauses."""
    feed = message(tm(modification(start={})))

    assert prefixes(check(feed, context())) == []


def test_every_offending_modification_is_reported_once():
    feed = message(
        tm(modification(), modification(start={"stop_id": "A"}), entity_id="one"),
        tm(modification(), entity_id="two"),
    )

    assert paths(check(feed, context())) == [
        "entity[0].trip_modifications.modifications[0]",
        "entity[1].trip_modifications.modifications[0]",
    ]


def test_a_feed_with_no_trip_modifications_reports_nothing():
    assert prefixes(check(message(entity("a"), entity("b", vehicle={})), context())) == []
