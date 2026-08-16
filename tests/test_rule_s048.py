"""S048, and the two readings its clause leaves open.

"Monotonically increasing" is read as non-decreasing, its ordinary mathematical
sense, so two replacement stops declaring the same offset are accepted. With no
oracle, the narrower rule is the one to ship: a strict reading would fire on
feeds the clause does not clearly forbid, and over-firing is the failure that
survives a green suite.

An absent `travel_time_to_stop` takes no part. The field is `optional` with no
declared default, so an absent one reads 0, and comparing that against a
preceding 120 would report a decrease the producer never wrote.

The grouping is the whole reason `walk_trip_modifications` has two views: a flat
stream of replacement stops would let the last stop of one modification be
compared against the first of the next, which the clause says nothing about.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.spec.s048 import check
from tripmodfixtures import context, message, modification, paths, prefixes
from tripmodfixtures import trip_modifications as tm

START = {"stop_id": "A"}
DECREASE = "travel_time_to_stop {} follows {} at an earlier replacement stop"


def stop(seconds: int | None = None, stop_id: str = "S") -> dict[str, object]:
    built: dict[str, object] = {"stop_id": stop_id}
    if seconds is not None:
        built["travel_time_to_stop"] = seconds
    return built


def test_an_increasing_run_is_not_reported():
    feed = message(tm(modification(stop(60), stop(120), stop(180), start=START)))

    assert prefixes(check(feed, context())) == []


def test_a_decrease_is_reported_against_the_stop_that_decreased():
    feed = message(tm(modification(stop(60), stop(30), start=START)))

    assert prefixes(check(feed, context())) == [DECREASE.format(30, 60)]
    assert paths(check(feed, context())) == [
        "entity[0].trip_modifications.modifications[0].replacement_stops[1]"
    ]


def test_equal_values_are_accepted():
    """Non-decreasing, which is what monotonically increasing means outside a
    context that says otherwise. Two stops thirty seconds apart round to one
    number, and the clause does not forbid that."""
    feed = message(tm(modification(stop(60), stop(60), start=START)))

    assert prefixes(check(feed, context())) == []


def test_a_negative_first_value_is_not_reported():
    """The clause's second half, "may only be a negative number if the first stop
    of the original trip is the reference stop", needs `start_stop_selector`
    resolved against a trip `SelectedTrips` names indirectly. The verdict file
    records that half as accepted-in-part; this rule cites the monotonicity half
    and must not half-enforce the other."""
    feed = message(tm(modification(stop(-30), stop(0), stop(45), start=START)))

    assert prefixes(check(feed, context())) == []


def test_a_stop_that_declares_no_travel_time_takes_no_part():
    feed = message(tm(modification(stop(60), stop(), stop(120), start=START)))

    assert prefixes(check(feed, context())) == []


def test_the_comparison_never_crosses_a_modification_boundary():
    """Flattened without the grouping, 120 followed by 30 reads as a decrease."""
    feed = message(
        tm(modification(stop(60), stop(120), start=START), modification(stop(30), start=START))
    )

    assert prefixes(check(feed, context())) == []


def test_each_stop_is_compared_against_the_highest_value_before_it():
    """A run of 60, 30, 40 has two stops out of order, not one: 40 is still below
    the 60 that precedes both. Comparing only against the immediate predecessor
    would call 40 an increase and let the sequence end below where it started."""
    feed = message(tm(modification(stop(60), stop(30), stop(40), start=START)))

    assert prefixes(check(feed, context())) == [DECREASE.format(30, 60), DECREASE.format(40, 60)]


def test_a_modification_with_one_replacement_stop_has_nothing_to_compare():
    assert prefixes(check(message(tm(modification(stop(60), start=START))), context())) == []
