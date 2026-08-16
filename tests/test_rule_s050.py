"""S050, the second of the index's two `definitional` clauses.

`1221#2` has no modal verb: "Dates on which the modifications occurs, in the
YYYYMMDD format." is a field description that fixes the field's value domain
rather than stating an obligation. Its ERROR comes from the kind, pinned by
`tools/scan_clauses.py`, not from a verb, and there is no advisory reading of a
value domain: a `service_dates` entry that is not a date is not an ill-advised
date, and no consumer can apply the modification at all.

Its clause id is `1221#2` although it is the first sentence on the line, because
declared clauses are numbered after the swept ones and `1221#1` is S049's.

E021 is the same predicate on `TripDescriptor.start_date` and is deliberately
more lenient, since it has a jar to match. `test_shared_servicedates.py` pins the
input where the two part company.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.rules.spec.s050 import check
from tripmodfixtures import context, message, paths, prefixes
from tripmodfixtures import trip_modifications as tm

NOT_A_DATE = "service_date {} is not a date in YYYYMMDD format"


@pytest.mark.parametrize("value", ["20260815", "20240229", "20231231"])
def test_a_real_date_is_not_reported(value: str):
    assert prefixes(check(message(tm(service_dates=[value])), context())) == []


@pytest.mark.parametrize("value", ["20170230", "20230229", "20261301", "2026-08-15", "", "next"])
def test_anything_that_is_not_a_calendar_date_is_reported(value: str):
    feed = message(tm(service_dates=[value]))

    assert prefixes(check(feed, context())) == [NOT_A_DATE.format(value)]


def test_february_the_thirtieth_is_reported_although_e021_accepts_it():
    """The one place this rule and E021 part company, and it is deliberate:
    E021 reproduces the jar's SMART resolver, which clamps to the 28th."""
    feed = message(tm(service_dates=["20170230"]))

    assert prefixes(check(feed, context())) == [NOT_A_DATE.format("20170230")]


def test_the_offending_value_is_located_by_its_position():
    feed = message(tm(service_dates=["20260815", "nope", "20260816"]))

    assert paths(check(feed, context())) == ["entity[0].trip_modifications.service_dates[1]"]


def test_a_trip_modifications_with_no_service_dates_reports_nothing():
    assert prefixes(check(message(tm()), context())) == []


def test_every_entity_is_read():
    feed = message(
        tm(service_dates=["bad1"], entity_id="one"), tm(service_dates=["bad2"], entity_id="two")
    )

    assert paths(check(feed, context())) == [
        "entity[0].trip_modifications.service_dates[0]",
        "entity[1].trip_modifications.service_dates[0]",
    ]
