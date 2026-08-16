"""S047, and the one thing the pinned `Stop` message cannot tell it.

`Stop` has fourteen fields at this pin and `location_type` is not among them:

    [f.name for f in SCHEMA.message("Stop").fields]

So a replacement stop defined by a realtime `Stop` entity has no location type to
read, and this rule treats it as routable rather than inventing an answer. The
assertion below pins that, so a `location_type` added at a later pin turns the
comment into a red test rather than leaving a silent gap.

E015 is the same predicate on `StopTimeUpdate.stop_id` and cannot reach this
message; the jar cannot show that by running, because `ReplacementStop` postdates
it.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s047 import check
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

START = {"stop_id": "A"}
STOPS = minimal(stops=stop_rows({"A": 0, "PLATFORM": 0, "STATION": 1, "ENTRANCE": 2}))


def test_the_pinned_stop_message_carries_no_location_type():
    assert "location_type" not in [field.name for field in SCHEMA.message("Stop").fields]


def test_a_replacement_stop_with_location_type_zero_is_not_reported(tmp_path: Path):
    feed = message(tm(modification({"stop_id": "PLATFORM"}, start=START)))

    assert prefixes(check(feed, rule_context(tmp_path, STOPS))) == []


def test_a_station_is_reported(tmp_path: Path):
    ctx = rule_context(tmp_path, STOPS)
    feed = message(tm(modification({"stop_id": "STATION"}, start=START)))

    assert prefixes(check(feed, ctx)) == ["stop_id STATION has location_type 1, not 0"]
    assert paths(check(feed, ctx)) == [
        "entity[0].trip_modifications.modifications[0].replacement_stops[0]"
    ]


def test_an_entrance_is_reported_with_its_own_location_type(tmp_path: Path):
    feed = message(tm(modification({"stop_id": "ENTRANCE"}, start=START)))

    assert prefixes(check(feed, rule_context(tmp_path, STOPS))) == [
        "stop_id ENTRANCE has location_type 2, not 0"
    ]


def test_a_stop_the_realtime_feed_defines_is_taken_as_routable(tmp_path: Path):
    """`Stop` declares no `location_type`, so there is nothing to disagree with.
    Reporting it would be this rule inventing a value the proto does not carry."""
    feed = message(
        entity("s", stop={"stop_id": "NEW"}), tm(modification({"stop_id": "NEW"}, start=START))
    )

    assert prefixes(check(feed, rule_context(tmp_path, STOPS))) == []


def test_a_stop_that_resolves_nowhere_is_s046s_finding_and_not_this_ones(tmp_path: Path):
    """One mistake, one clause. A stop_id in neither feed has no location type
    at all, and charging it to both rules would double-report it."""
    feed = message(tm(modification({"stop_id": "GONE"}, start=START)))

    assert prefixes(check(feed, rule_context(tmp_path, STOPS))) == []


def test_every_replacement_stop_is_checked(tmp_path: Path):
    feed = message(
        tm(
            modification({"stop_id": "PLATFORM"}, {"stop_id": "STATION"}, start=START),
            modification({"stop_id": "ENTRANCE"}, start=START),
        )
    )

    assert prefixes(check(feed, rule_context(tmp_path, STOPS))) == [
        "stop_id STATION has location_type 1, not 0",
        "stop_id ENTRANCE has location_type 2, not 0",
    ]
