"""`TripModifications.service_dates`, parsed strictly and dated against the run.

S050 reports a value that is not a date and S049 reports one too far ahead, so
both need the same parse and neither may use `_shared/timeformats.py`. That
module reproduces `DateTimeFormatter` resolving SMART, which accepts `20170230`
as the 28th, because E021 has to match the jar byte for byte. These two rules
have no jar to match, so importing the lenient helper would carry a compat bug
into the tier whose whole purpose is not to have one.
"""

from __future__ import annotations

import datetime as dt

import pytest

from gtfs_rt_validator.rules._shared.servicedates import parse_service_date, run_date
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from tripmodfixtures import context


@pytest.mark.parametrize(
    "value",
    ["20260815", "20240229", "00010101", "99991231"],
)
def test_a_real_date_parses(value: str):
    assert parse_service_date(value) is not None


@pytest.mark.parametrize(
    "value",
    [
        "20170230",  # February 30th, which E021 accepts and this refuses
        "20230229",  # not a leap year
        "20261301",  # month 13
        "2026-08-15",
        "2026815",
        "20260815 ",
        "20260815X",
        "",
        "abcdefgh",
        "٢٠٢٦٠٨١٥",  # Arabic-Indic digits, which `str.isdigit` would take
    ],
)
def test_anything_that_is_not_an_eight_digit_calendar_date_is_refused(value: str):
    assert parse_service_date(value) is None


def test_february_the_thirtieth_is_where_this_parts_company_with_e021():
    """`timeformats.is_valid_date_format` accepts it, because the jar's resolver
    clamps to the previous valid day. Measured there, not assumed here."""
    from gtfs_rt_validator.rules._shared.timeformats import is_valid_date_format

    assert is_valid_date_format("20170230")
    assert parse_service_date("20170230") is None


def test_the_run_date_is_the_clocks_day_in_the_feeds_own_zone():
    """1700000000000 ms is 2023-11-14T22:13:20Z, which is still the 14th in New
    York and already the 15th in Tokyo. A rule comparing service dates against a
    UTC day would be a day out for every agency west of Greenwich."""
    reading = Reading(1_700_000_000_000, ClockSource.FIXED)

    assert run_date(context(clock=reading, timezone="America/New_York")) == dt.date(2023, 11, 14)
    assert run_date(context(clock=reading, timezone="Asia/Tokyo")) == dt.date(2023, 11, 15)


def test_a_zone_id_the_tz_database_does_not_know_falls_back_rather_than_raising():
    """`_shared/zones.py` answers `getTimeZone`'s three steps, including the
    custom `GMT+hh:mm` grammar real `agency.txt` files carry. Nothing here may
    raise on a feed's own string."""
    reading = Reading(1_700_000_000_000, ClockSource.FIXED)

    assert run_date(context(clock=reading, timezone="GMT+14:00")) == dt.date(2023, 11, 15)
    assert run_date(context(clock=reading, timezone="NotAZone")) == dt.date(2023, 11, 14)
