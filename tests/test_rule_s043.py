"""S043, and the reason it is not E011.

Both rules assert a `stop_id` is in `stops.txt`, and the boundary is the field
rather than the question: E011 walks a StopTimeUpdate, a VehiclePosition and an
alert's informed entities (`StopValidator.java:53-101`), and `TripModifications`
is in none of the three and is not in the 2015 schema E011 decodes with at all.
`rules/upstream/e011.py` must not grow a `TripModifications` branch.

The earlier claim that a `StopSelector.stop_id` may also resolve to a `Stop`
entity of the same feed was wrong, and the fixtures below now say so. `:1242`
names `stops.txt` and no second place; `:1259` names the second place for
`ReplacementStop.stop_id`, which is S046's field and keeps the widened
resolution; and `:1163` says a `start_stop_selector` names a stop_time of the
**original** trip, which a stop this feed has just invented is not.

The jar cannot refute the boundary by running, and it is worth being plain about
why: `StopSelector` postdates it, so the whole `TripModifications` entity decodes
as unknown fields there and the jar emits nothing for any fixture in this file.
That is an absence of evidence, not evidence of absence, and the boundary rests
on reading `StopValidator.java` rather than on a green differential.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.spec.s043 import check
from tripmodfixtures import (
    entity,
    message,
    minimal,
    modification,
    paths,
    prefixes,
    rule_context,
    stop_rows,
)
from tripmodfixtures import trip_modifications as tm

UNRESOLVED = "stop_id {} is not in stops.txt"

IS_NEW = ", and the Stop entity of this feed that defines it is a new stop"


def test_a_stop_id_in_stops_txt_resolves(tmp_path: Path):
    ctx = rule_context(tmp_path, minimal(stops=stop_rows({"A": 0})))
    feed = message(tm(modification(start={"stop_id": "A"})))

    assert prefixes(check(feed, ctx)) == []


def test_a_stop_id_in_neither_place_is_reported(tmp_path: Path):
    ctx = rule_context(tmp_path, minimal(stops=stop_rows({"A": 0})))
    feed = message(tm(modification(start={"stop_id": "Z"})))

    assert prefixes(check(feed, ctx)) == [UNRESOLVED.format("Z")]
    assert paths(check(feed, ctx)) == [
        "entity[0].trip_modifications.modifications[0].start_stop_selector"
    ]


def test_a_stop_defined_only_by_a_stop_entity_of_the_same_feed_does_not_resolve(tmp_path: Path):
    """`:1242` names one place, and a `Stop` entity is not it. `:1163` says why:
    a `start_stop_selector` names "the first stop_time of the original trip", and
    a stop this feed invents is not on the original trip. That is the difference
    from `ReplacementStop.stop_id`, whose own comment at `:1259` does permit a
    realtime `Stop`, and it is why S046 keeps the widened resolution."""
    ctx = rule_context(tmp_path, minimal())
    feed = message(entity("s", stop={"stop_id": "Z"}), tm(modification(start={"stop_id": "Z"})))

    assert prefixes(check(feed, ctx)) == [UNRESOLVED.format("Z") + IS_NEW]


def test_the_stop_entity_may_follow_the_reference_that_names_it(tmp_path: Path):
    """`FeedEntity` ordering is not specified anywhere in the proto, so the
    entity that defines a stop may come after the reference to it. The index is
    built from the whole message for exactly that reason, and this rule still
    reads it: not to resolve the id, which only `stops.txt` can, but to say
    which mistake was made."""
    ctx = rule_context(tmp_path, minimal())
    feed = message(tm(modification(start={"stop_id": "Z"})), entity("s", stop={"stop_id": "Z"}))

    assert prefixes(check(feed, ctx)) == [UNRESOLVED.format("Z") + IS_NEW]


def test_both_selectors_are_resolved(tmp_path: Path):
    ctx = rule_context(tmp_path, minimal(stops=stop_rows({"A": 0})))
    feed = message(tm(modification(start={"stop_id": "Y"}, end={"stop_id": "Z"})))

    assert prefixes(check(feed, ctx)) == [UNRESOLVED.format("Y"), UNRESOLVED.format("Z")]


def test_a_selector_that_names_only_a_stop_sequence_is_not_this_rules_business(tmp_path: Path):
    ctx = rule_context(tmp_path, minimal())
    feed = message(tm(modification(start={"stop_sequence": 4})))

    assert prefixes(check(feed, ctx)) == []
