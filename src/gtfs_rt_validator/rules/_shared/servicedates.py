"""`TripModifications.service_dates`: parsed strictly, and dated against the run.

S050 reports a value that is not a date and S049 reports one more than a week
ahead, so both need the same parse and the second needs to know what day the run
is on.

**Deliberately not `_shared/timeformats.py`.** `is_valid_date_format` reproduces
`DateTimeFormatter` resolving SMART, which clamps an impossible calendar date to
the previous valid day and so accepts `20170230`. That is correct there and
measured against a JDK run, because E021 has to match the jar byte for byte.
These two rules have no jar to match, so reusing it would carry a compat bug into
the tier whose whole purpose is not to have one. The plan says so explicitly and
`tests/test_shared_servicedates.py` pins the one input where the two part
company.

**The run's day is the feed's day, not UTC's.** A service date is a calendar day
in the agency's own zone, so a rule comparing one against a UTC day would be a
day out for every agency west of Greenwich for part of each day. `zones.py`
resolves the id the way `TimeZone.getTimeZone` does, which matters because real
`agency.txt` files carry custom `GMT+hh:mm` ids that `zoneinfo` alone refuses,
and because nothing here may raise on a string a feed supplied.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING

from gtfs_rt_validator.rules._shared.zones import java_time_zone

if TYPE_CHECKING:  # Type-only: nothing under `rules/` may import the runner at
    # run time, because it reaches the static layer and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["FORMAT", "parse_service_date", "run_date"]

#: What `1221#2` fixes as the field's value domain, in the form a reader of a
#: report will recognise.
FORMAT = "YYYYMMDD"

_MILLIS_PER_SECOND = 1000

# ASCII digits only. `str.isdigit` accepts Arabic-Indic and full-width digits,
# which `strptime` then refuses anyway, but by raising rather than answering; the
# gate is here so the refusal is this module's and reads the same for every
# non-date.
_EIGHT_ASCII_DIGITS = re.compile(r"\A[0-9]{8}\Z")


def parse_service_date(value: str) -> dt.date | None:
    """The date `value` names, or `None` if it names none.

    Strict: February 30th is not a date, and neither is a string with anything
    around the eight digits. `datetime.date` does the calendar arithmetic and
    raises on an impossible day, so leap years come from the stdlib rather than
    from a rule. It is `date` rather than `strptime` because a service date is a
    calendar day with no instant behind it, and building a naive datetime here
    would be inventing a midnight in a zone this function is not given.
    """
    if not _EIGHT_ASCII_DIGITS.fullmatch(value):
        return None
    try:
        return dt.date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None


def run_date(ctx: RuleContext) -> dt.date:
    """The calendar day the run's clock falls on, in the feed's own zone.

    Integer seconds rather than `millis / 1000`, so the conversion is exact and
    floors the way a clock before the epoch needs it to.
    """
    seconds = ctx.clock.millis // _MILLIS_PER_SECOND
    return dt.datetime.fromtimestamp(seconds, tz=java_time_zone(ctx.timezone)).date()
