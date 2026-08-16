"""E044: an arrival or departure that carries neither a delay nor a time.

Ported from `validation/rules/StopTimeUpdateValidator.java:368-393`, called once
per stop_time_update at `:171`:

```java
if (stopTimeUpdate.hasScheduleRelationship() && scheduleRelationship.equals(SKIPPED)) {
    return;   // see upstream issue #243
}
String id = getTripId(entity, tripUpdate) + " " + getStopTimeUpdateId(stopTimeUpdate);
if (stopTimeUpdate.hasArrival())   checkE044StopTimeEvent(getArrival(),   id + " arrival",   errors);
if (stopTimeUpdate.hasDeparture()) checkE044StopTimeEvent(getDeparture(), id + " departure", errors);
```

and `checkE044StopTimeEvent` (`:389-393`) fires when
`!stopTimeEvent.hasDelay() && !stopTimeEvent.hasTime()`.

**NO_DATA is not exempt here, unlike E043.** Only SKIPPED returns early, which
upstream added for issue #243: a skipped stop has no prediction to make, so its
arrival and departure are optional and empty ones are not a finding. A NO_DATA
stop_time_update that supplies an empty arrival is still reported, and it is
reported by E042 as well for having an arrival at all.

Both events are tested independently, so one stop_time_update can give two
occurrences, arrival first.
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

RULE_ID = "E044"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """Up to two per stop_time_update the shared walk reached and did not skip."""
    return occurrences_for(RULE_ID, message, ctx)
