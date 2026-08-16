"""E023: a start_time that is not the trip's first GTFS arrival_time.

`checkE023` in `validation/rules/TripDescriptorValidator.java:287-304`, reached
only from the `else` arm of the trip-lookup, so the trip is known to be in
`trips.txt`, and only when `hasStartTime()` (`:112` and `:160`).

Frequency-based trips are exempt on both sides: a trip_id in
`exactTimesZeroTripIds` or in `exactTimesOneTrips` returns before anything is
compared. A trip with no `stop_times.txt` rows returns too, which is the fix for
upstream's issue #217 and is regression-tested there with a trip_id that exists
in neither file.

**It reads element zero only.** `trip_stop_times` is sorted by `stop_sequence`,
so element zero is the first stop, and this rule must not be folded into the
stateful stop_time_update walk: it never advances.

**The negative sentinel reaches output bytes.** onebusaway's
`StopTime.getArrivalTime()` is a primitive `int` whose unset value is -999, and
`secondsAfterMidnightToClock(-999)` renders `"00:-16:-39"` under Java's
truncating division and sign-of-dividend remainder. The comparison then fails
for every real start_time and that string is printed. `_shared/times.py` does
the arithmetic Java's way and pins -999 explicitly; the sibling loader hands
back `None` for the same cell, and `_shared/trip_descriptor_checks.py` restores
the sentinel before formatting.

The prefix is `"GTFS-rt " + getVehicleAndTripIdText(entity) + " start_time is "
+ startTime + " and GTFS initial arrival_time is " + formattedArrivalTime`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.walk_trip_descriptor import trip_descriptors
from gtfs_rt_validator.rules._shared.walks import events_for
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "E023"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
