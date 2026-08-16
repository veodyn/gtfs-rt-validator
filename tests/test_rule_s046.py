"""S046, and the upstream typo its citation has to carry.

`1261#1` says "`Shape` entity" where it means `Stop`, copy-pasted from the
identical sentence at `:1202`. The sentence above it and `_shared/feed_index.py`'s
`Stop` index both settle what is meant, but the citation gate compares bytes, so
the `source=` string quotes the proto as written. Correcting the typo would fail
the build, and correcting it in the index would be editing a generated file.

Same question as S043, different message, different severity: `1242#1` says
`must` and this one says `should`.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.spec.s046 import CLAUSE, check
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

UNRESOLVED = "stop_id {} is in neither stops.txt nor a Stop entity of this feed"
CONFUSED = ", and is the id of a FeedEntity rather than the stop_id inside one"

START = {"stop_id": "A"}


def test_the_citation_quotes_the_upstream_typo_rather_than_correcting_it():
    """`Shape` is what the proto says at `:1261` and `Stop` is what it means.
    The gate compares bytes, so the rule quotes what is there."""
    assert "`Shape` entity" in CLAUSE
    assert "`stop_id` inside the entity" in CLAUSE


def test_a_replacement_stop_in_stops_txt_resolves(tmp_path: Path):
    ctx = rule_context(tmp_path, minimal(stops=stop_rows({"A": 0, "B": 0})))
    feed = message(tm(modification({"stop_id": "B"}, start=START)))

    assert prefixes(check(feed, ctx)) == []


def test_a_replacement_stop_in_neither_place_is_reported(tmp_path: Path):
    ctx = rule_context(tmp_path, minimal(stops=stop_rows({"A": 0})))
    feed = message(tm(modification({"stop_id": "Z"}, start=START)))

    assert prefixes(check(feed, ctx)) == [UNRESOLVED.format("Z")]
    assert paths(check(feed, ctx)) == [
        "entity[0].trip_modifications.modifications[0].replacement_stops[0]"
    ]


def test_a_stop_added_by_a_stop_entity_of_the_same_feed_resolves(tmp_path: Path):
    """What `:1260` describes and what E011 cannot see: a feed that defines a new
    stop and then routes a modified trip through it is correct."""
    ctx = rule_context(tmp_path, minimal(stops=stop_rows({"A": 0})))
    feed = message(
        entity("s", stop={"stop_id": "NEW"}), tm(modification({"stop_id": "NEW"}, start=START))
    )

    assert prefixes(check(feed, ctx)) == []


def test_the_feed_entity_id_written_instead_of_the_stop_id_is_named_as_such(tmp_path: Path):
    ctx = rule_context(tmp_path, minimal(stops=stop_rows({"A": 0})))
    feed = message(
        entity("s", stop={"stop_id": "NEW"}), tm(modification({"stop_id": "s"}, start=START))
    )

    assert prefixes(check(feed, ctx)) == [UNRESOLVED.format("s") + CONFUSED]


def test_a_replacement_stop_with_no_stop_id_is_not_reported(tmp_path: Path):
    ctx = rule_context(tmp_path, minimal(stops=stop_rows({"A": 0})))
    feed = message(tm(modification({"travel_time_to_stop": 60}, start=START)))

    assert prefixes(check(feed, ctx)) == []


def test_every_replacement_stop_of_every_modification_is_resolved(tmp_path: Path):
    ctx = rule_context(tmp_path, minimal(stops=stop_rows({"A": 0})))
    feed = message(
        tm(
            modification({"stop_id": "X"}, start=START),
            modification({"stop_id": "Y"}, {"stop_id": "Z"}, start=START),
        )
    )

    assert prefixes(check(feed, ctx)) == [
        UNRESOLVED.format("X"),
        UNRESOLVED.format("Y"),
        UNRESOLVED.format("Z"),
    ]
