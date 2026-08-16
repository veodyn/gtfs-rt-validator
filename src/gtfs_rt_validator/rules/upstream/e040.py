"""E040: a stop_time_update names neither a stop_id nor a stop_sequence.

Ported from `validation/rules/StopTimeUpdateValidator.java:292-296`, called once
per stop_time_update at `:168`:

```java
if (!stopTimeUpdate.hasStopSequence() && !stopTimeUpdate.hasStopId()) {
    RuleUtils.addOccurrence(E040, GtfsUtils.getTripId(entity, tripUpdate), errors, _log);
}
```

**The prefix identifies the trip, not the stop_time_update.** There is nothing
in a stop_time_update with neither field to name it by, and upstream does not
reach for its index, so a TripUpdate with three bare stop_time_updates produces
three byte-identical occurrences. That is not de-duplicated anywhere.

Why it still lives in the shared walk despite having no state of its own: the
`break` at `:180` decides *which* stop_time_updates are reached at all, and a
rule looping independently would report E040 for stop_time_updates the jar
abandoned.
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

RULE_ID = "E040"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One per stop_time_update the shared walk reached that names neither field."""
    return occurrences_for(RULE_ID, message, ctx)
