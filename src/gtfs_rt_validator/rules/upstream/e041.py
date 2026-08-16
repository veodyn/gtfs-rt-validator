"""E041: a TripUpdate carries no stop_time_updates and is not CANCELED.

Ported from `validation/rules/StopTimeUpdateValidator.java:305-315`, called at
`:79` **before anything else** in the TripUpdate, ahead even of the trip_id
lookup:

```java
if (tripUpdate.getStopTimeUpdateCount() < 1) {
    if (tripUpdate.hasTrip() && tripUpdate.getTrip().hasScheduleRelationship()
            && tripUpdate.getTrip().getScheduleRelationship().equals(CANCELED)) {
        return;
    }
    RuleUtils.addOccurrence(E041, GtfsUtils.getTripId(entity, tripUpdate), errors, _log);
}
```

**The schedule_relationship gap, stated precisely.** The exemption needs a
*recognised* CANCELED, and CANCELED is in the 2015 enum, so it works identically
under both schemas. What the two-schema decoder changes is the post-2015 values:
protobuf 2.6.1 drops an unrecognised enum value into the unknown-field set, so
`hasScheduleRelationship()` is false and a TripUpdate whose trip is DUPLICATED
or DELETED with no stop_time_updates is reported. It was never exempt under
either reading, so nothing is *lost* here; what changes is that under a modern
schema the field is visible and under the 2015 one it is not, and every other
rule that reads this field sees the same thing.

`getStopTimeUpdateCount() < 1` rather than `isEmpty()`, and it is a count of a
repeated field, so `len(...)` is the port rather than `has(...)`.

At most one occurrence per TripUpdate.
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

RULE_ID = "E041"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One per empty TripUpdate the shared walk saw that was not CANCELED."""
    return occurrences_for(RULE_ID, message, ctx)
