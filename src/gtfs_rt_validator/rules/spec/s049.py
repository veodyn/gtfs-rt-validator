"""S049: a detour transmitted for a day outside the week ahead.

Cites `1221#1`, the second sentence of the `service_dates` comment:

> Producers SHOULD only transmit detours occurring within the next week.

`SHOULD` is where the WARNING comes from.

**The seventh day is inside the week.** "Within the next week" includes it, so
the eighth is the first day reported and the boundary is a `>` rather than a
`>=`. This is one of the three off-by-one boundaries settled in writing before
any rule was written.

**The run's day, in the feed's own zone.** `ctx.clock` is the reading the runner
derived for this file, never `System.currentTimeMillis`, which is what keeps an
archive replay reproducible; `_shared/servicedates.py` turns it into a calendar
day in the agency's zone, because a service date is a day rather than an instant
and a UTC comparison would be a day out for every agency west of Greenwich for
part of each day.

**Both halves, because "only ... within" is a two-sided bound.** An earlier draft
read the sentence as a lookahead cap and let every past date through, on the
grounds that a stale detour is a different complaint no clause in the pin makes.
That reading does not survive the word "only": a detour that ran in 2020 is not
one occurring within the next week, so transmitting it is exactly what the
sentence tells a producer not to do. The granularity settles the rest. This rule
already reads the clause per `service_dates` value rather than per detour, firing
on the far dates of a `TripModifications` whose near dates are fine, and a window
checked per value has two edges. So the day of the run and the seven after it are
silent, and everything on either side reports.

**The two edges get different wording.** They are different producer mistakes:
publishing further ahead than a week, and never pruning a day that has passed. An
occurrence telling a reader that 20200101 is "more than 7 days after" today would
describe neither, and a report is triaged by its text.

**A value that is not a date is S050's finding.** It has no distance from today
to measure, and charging one mistake to two clauses is the double-reporting
`tests/test_tier_overlap.py` exists to prevent.

`TripModifications` postdates the jar, so nothing in the differential can confirm
this rule or refute its declared overlap, which is none: `OVERLAP` in
`tests/test_tier_overlap.py` names no upstream rule for S049.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.manifest import Severity
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.servicedates import parse_service_date, run_date
from gtfs_rt_validator.rules._shared.walk_trip_modifications import trip_modifications
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    import datetime as dt

    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S049"

CLAUSE = "spec: Producers SHOULD only transmit detours occurring within the next week."

#: "The next week", counted in days from the day the run is on. Inclusive: the
#: seventh day is within the week and the eighth is not.
WEEK_IN_DAYS = 7

TOO_FAR = "service_date {value} is more than {days} days after {today}, the day of this run"
ELAPSED = "service_date {value} is before {today}, the day of this run"


@rule(RULE_ID, source=CLAUSE, severity=Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Every `service_dates` value of every `TripModifications`."""
    walked = trip_modifications(message, ctx)
    if not walked:
        return
    today = run_date(ctx)
    for record in walked:
        for position, value in enumerate(record.owner.get("service_dates")):
            prefix = _outside_the_week(value, today)
            if prefix is None:
                continue
            yield Occurrence(
                RULE_ID, prefix, {ENTITY_PATH_KEY: f"{record.path}.service_dates[{position}]"}
            )


def _outside_the_week(value: str, today: dt.date) -> str | None:
    """What to say about one `service_dates` value, or `None` if it is inside.

    A value that is not a date is S050's finding and never this one: it has no
    distance from today to measure, and charging one mistake to two clauses is
    double-reporting.
    """
    written = parse_service_date(value)
    if written is None:
        return None
    days = (written - today).days
    if days > WEEK_IN_DAYS:
        return TOO_FAR.format(value=value, days=WEEK_IN_DAYS, today=f"{today:%Y%m%d}")
    if days < 0:
        return ELAPSED.format(value=value, today=f"{today:%Y%m%d}")
    return None
