"""E042: a NO_DATA stop_time_update still carries an arrival or a departure.

Ported from `validation/rules/StopTimeUpdateValidator.java:325-337`, called once
per stop_time_update at `:169`:

```java
if (stopTimeUpdate.hasScheduleRelationship() && stopTimeUpdate.getScheduleRelationship().equals(NO_DATA)) {
    String id = getTripId(entity, tripUpdate) + " " + getStopTimeUpdateId(stopTimeUpdate);
    if (stopTimeUpdate.hasArrival())   { ... id + " has arrival" ... }
    if (stopTimeUpdate.hasDeparture()) { ... id + " has departure" ... }
}
```

**Two independent tests, not an either-or.** A NO_DATA stop_time_update carrying
both an arrival and a departure gives two occurrences, arrival first.

**This is `StopTimeUpdate.ScheduleRelationship`, a different enum from the trip
one.** The 2015 schema has three values (SCHEDULED, SKIPPED, NO_DATA) and
today's has four; an unrecognised value reads as absent under the 2015 schema,
so `hasScheduleRelationship()` is false and the rule cannot fire for it.

`getStopTimeUpdateId` prefers stop_sequence and falls back to an **unguarded**
`getStopId()`, so a stop_time_update with neither renders `"stop_id "` with a
trailing space. That belongs to `_shared/ids.py` and is not this rule's to fix.
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

RULE_ID = "E042"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """Up to two per NO_DATA stop_time_update the shared walk reached."""
    return occurrences_for(RULE_ID, message, ctx)
