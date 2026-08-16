"""E045: the GTFS row at this stop_sequence names a different stop_id.

Ported from `validation/rules/StopTimeUpdateValidator.java:405-413`, called from
**inside** the walk's `while` loop at `:129`, and only there:

```java
if (stopTimeUpdate.hasStopId() && !stop.getId().getId().equals(stopTimeUpdate.getStopId())) {
    String tripId       = "GTFS-rt " + getTripId(entity, tripUpdate) + " ";
    String stopSequence = "stop_sequence " + stopTimeUpdate.getStopSequence();
    String stopId       = "stop_id " + stopTimeUpdate.getStopId();
    String gtfsSummary  = " but GTFS stop_sequence " + gtfsStopSequence
                        + " has stop_id " + stop.getId().getId();
    ... tripId + stopSequence + " has " + stopId + gtfsSummary ...
}
```

**Reachable only on a stop_sequence match.** The call site sits inside
`if (gtfsStopSequence == stopTimeUpdate.getStopSequence())`, so the feed's
stop_sequence and `gtfsStopSequence` are always the same number in the rendered
text even though the Java interpolates both. A stop_sequence that matches
nothing walks to the end of `stop_times.txt` and reports E051 instead, and a
TripUpdate whose trip is absent from `stop_times.txt` reaches neither.

**`stop.getId().getId()` is the bare stop_id.** `getId()` on the `Stop` returns
an onebusaway `AgencyAndId` whose own `toString()` would join the agency with an
underscore; the second `getId()` unwraps it. E011 has the same trap from the
other direction and its module says more.

The space after the trip id comes from the `tripId` local ending in one, which
is why the rendered text has exactly one space there and not two.

At most one occurrence per stop_time_update.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.rules._shared.walk_stop_time_updates import occurrences_for
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only, both of them. `runner.context` reaches the static
    # layer and the sibling package, and nothing under `rules/` may import that
    # at run time; `tests/test_only_adapter_touches_the_sibling.py` is the check.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "E045"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One per stop_sequence match the shared walk made with a mismatched stop_id."""
    return occurrences_for(RULE_ID, message, ctx)
