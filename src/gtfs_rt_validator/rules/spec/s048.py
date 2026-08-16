"""S048: `travel_time_to_stop` going backwards inside one `Modification`.

Cites `1257#1`, and only its first half:

> This value MUST be monotonically increasing and may only be a negative number
> if the first stop of the original trip is the reference stop.

Capital `MUST` is where the ERROR comes from. The verdict file records this as
`rule_in_part`: the negative-number half needs the modification's
`start_stop_selector` resolved against a trip that `SelectedTrips` names
indirectly, which is a second walk, and it is left out of the first release
rather than half-implemented. So a negative value is not reported
here at all, and the test says so, because a rule quietly enforcing half a clause
it does not cite is worse than one that does not enforce it.

**Three readings this rule had to pick between, and the reasons.**

1. **Non-decreasing, not strictly increasing.** "Monotonically increasing" has
   both senses in circulation and the proto settles neither. Two replacement
   stops thirty seconds apart round to one whole-second offset, so equality is a
   feed shape the clause does not clearly forbid, and with no oracle the narrower
   rule is the one that ships. This is the same move S029 makes at `:689` and it
   is stated rather than left to be discovered.
2. **An absent `travel_time_to_stop` takes no part.** The field is `optional`
   with no declared default, so an absent one reads 0; comparing that 0 against a
   preceding 120 would report a decrease the producer never wrote.
3. **Each declared value is compared against the highest one before it**, not
   against its immediate predecessor. A run of 60, 30, 40 has two stops out of
   order: 40 is an increase on 30 and still below the 60 that precedes both, and
   a rule that compared neighbours would report the first and call the second
   fine while the sequence ends below where it started.

The grouping comes from `_shared/walk_trip_modifications.py`, which keeps it for
this rule: a flat stream of replacement stops would let the last stop of one
modification be compared against the first of the next.

`ReplacementStop` postdates the jar, so nothing in the differential can confirm
this rule or refute the claim that no upstream rule borders it, which
`tests/test_tier_overlap.py` records by leaving S048 out of `OVERLAP`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.manifest import Severity
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_trip_modifications import modifications
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S048"

CLAUSE = (
    "spec: This value MUST be monotonically increasing and may only be a negative number "
    "if the first stop of the original trip is the reference stop."
)

FIELD = "travel_time_to_stop"


@rule(RULE_ID, source=CLAUSE, severity=Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """One run per modification, over the stops that declare the field."""
    for record in modifications(message, ctx):
        highest: int | None = None
        for found in record.replacement_stops:
            if not found.stop.has(FIELD):
                continue
            seconds = found.stop.get(FIELD)
            if highest is not None and seconds < highest:
                yield Occurrence(
                    RULE_ID,
                    f"{FIELD} {seconds} follows {highest} at an earlier replacement stop",
                    {ENTITY_PATH_KEY: found.path},
                )
            else:
                highest = seconds
