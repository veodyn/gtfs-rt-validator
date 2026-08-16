"""S050: a `service_dates` value that is not a date.

Cites `1221#2`:

> Dates on which the modifications occurs, in the YYYYMMDD format.

**A `definitional` clause, and one of exactly two in the index.** The sentence
carries no modal verb and should not: it fixes the field's value domain rather
than stating an obligation. Its ERROR therefore comes from the clause's kind,
which `tools/scan_clauses.py` pins and refuses to let be anything else, and the
argument is that there is no advisory reading of a value domain. A
`service_dates` entry that is not a date is not an ill-advised date; nothing
downstream can apply the modification at all.

The clause id is `1221#2` although this is the first sentence on the line.
Declared clauses are numbered after the swept ones, and `1221#1` is S049's; the
alternative would have renumbered a verdict key for a clause that did not change.

**Deliberately stricter than E021, which is the same predicate on
`TripDescriptor.start_date`.** E021 reproduces `DateTimeFormatter` resolving
SMART, which clamps February 30th to the 28th and so accepts it, because it has a
jar to match byte for byte. This rule has none, so it parses strictly through
`_shared/servicedates.py`. Sharing `_shared/timeformats.py` here would import a
compat bug into the tier whose whole purpose is not to have one.

`TripModifications` postdates the jar, so nothing in the differential can confirm
this rule.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.manifest import Severity
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.servicedates import FORMAT, parse_service_date
from gtfs_rt_validator.rules._shared.walk_trip_modifications import trip_modifications
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S050"

CLAUSE = "spec: Dates on which the modifications occurs, in the YYYYMMDD format."


@rule(RULE_ID, source=CLAUSE, severity=Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Every `service_dates` value of every `TripModifications`."""
    for record in trip_modifications(message, ctx):
        for position, value in enumerate(record.owner.get("service_dates")):
            if parse_service_date(value) is None:
                yield Occurrence(
                    RULE_ID,
                    f"service_date {value} is not a date in {FORMAT} format",
                    {ENTITY_PATH_KEY: f"{record.path}.service_dates[{position}]"},
                )
