"""E043: a stop_time_update has neither an arrival nor a departure.

Ported from `validation/rules/StopTimeUpdateValidator.java:347-357`, called once
per stop_time_update at `:170`:

```java
if (!stopTimeUpdate.hasArrival() && !stopTimeUpdate.hasDeparture()) {
    if (stopTimeUpdate.hasScheduleRelationship()
            && (scheduleRelationship.equals(SKIPPED) || scheduleRelationship.equals(NO_DATA))) {
        return;
    }
    ... getTripId(entity, tripUpdate) + " " + getStopTimeUpdateId(stopTimeUpdate) ...
}
```

**SKIPPED and NO_DATA are both exempt here, and E044 exempts only SKIPPED.**
That asymmetry between the two rules is deliberate upstream: a NO_DATA
stop_time_update need not predict anything, but if it does predict something the
prediction still has to carry a delay or a time. Do not "fix" one to match the
other.

The presence test is `hasArrival()`, not "an arrival with anything in it": an
arrival present but empty satisfies E043 and is precisely what E044 reports.
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

RULE_ID = "E043"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One per stop_time_update the shared walk reached that predicted nothing."""
    return occurrences_for(RULE_ID, message, ctx)
