"""S049 at its boundary, which is exactly seven days.

"Within the next week" includes the seventh day, so the eighth is the first one
reported. This is one of the three off-by-one boundaries settled in writing
before any rule was written.

The clock is fixed, so nothing here depends on when the suite runs: 1700000000000
milliseconds is 2023-11-14T22:13:20Z, which is the 14th in New York.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.spec.s049 import check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from tripmodfixtures import context, message, paths, prefixes
from tripmodfixtures import trip_modifications as tm

READING = Reading(1_700_000_000_000, ClockSource.FIXED)
TOO_FAR = "service_date {} is more than 7 days after 20231114, the day of this run"
ELAPSED = "service_date {} is before 20231114, the day of this run"


def ctx():
    return context(clock=READING, timezone="America/New_York")


def test_today_is_within_the_week():
    assert prefixes(check(message(tm(service_dates=["20231114"])), ctx())) == []


def test_the_seventh_day_is_within_the_week():
    assert prefixes(check(message(tm(service_dates=["20231121"])), ctx())) == []


def test_the_eighth_day_is_reported():
    feed = message(tm(service_dates=["20231122"]))

    assert prefixes(check(feed, ctx())) == [TOO_FAR.format("20231122")]
    assert paths(check(feed, ctx())) == ["entity[0].trip_modifications.service_dates[0]"]


def test_a_date_in_the_past_is_reported_too():
    """ "Only ... within the next week" is a two-sided bound, and a detour that
    ran in 2020 is not occurring within it. The rule already reads the clause per
    service date rather than per detour, firing on the far dates of a run that
    also has near ones, so the same granularity has to answer the near side."""
    feed = message(tm(service_dates=["20200101"]))

    assert prefixes(check(feed, ctx())) == [ELAPSED.format("20200101")]
    assert paths(check(feed, ctx())) == ["entity[0].trip_modifications.service_dates[0]"]


def test_yesterday_is_the_first_day_reported_on_the_near_side():
    """The boundary the future half already has, on the other side: the day of
    the run is within the week and the day before it is not."""
    assert prefixes(check(message(tm(service_dates=["20231113"])), ctx())) == [
        ELAPSED.format("20231113")
    ]


def test_an_elapsed_date_does_not_borrow_the_far_sides_wording():
    """The two halves are different producer mistakes: publishing further ahead
    than a week, and never pruning a date that has passed. An occurrence saying
    20200101 is "more than 7 days after" the run would describe neither."""
    (found,) = check(message(tm(service_dates=["20200101"])), ctx())

    assert "more than" not in found.prefix


def test_a_value_that_is_not_a_date_is_left_to_s050():
    """One mistake, one clause. `20231399` has no distance from today at all."""
    assert prefixes(check(message(tm(service_dates=["20231399"])), ctx())) == []


def test_every_offending_date_of_every_entity_is_reported():
    feed = message(
        tm(service_dates=["20231121", "20231201"], entity_id="one"),
        tm(service_dates=["20240101"], entity_id="two"),
    )

    assert prefixes(check(feed, ctx())) == [TOO_FAR.format("20231201"), TOO_FAR.format("20240101")]
    assert paths(check(feed, ctx())) == [
        "entity[0].trip_modifications.service_dates[1]",
        "entity[1].trip_modifications.service_dates[0]",
    ]


def test_the_day_the_run_is_on_is_read_in_the_feeds_own_zone():
    """Same instant, one zone further east, and the run is already on the 15th,
    which moves the boundary with it."""
    tokyo = context(clock=READING, timezone="Asia/Tokyo")

    assert prefixes(check(message(tm(service_dates=["20231122"])), tokyo)) == []
