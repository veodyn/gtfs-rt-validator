"""E037: two stop_time_updates in a row carry the same stop_id.

Ported from `validation/rules/StopTimeUpdateValidator.java:268-282`, called from
the walk at `:108-110`:

```java
if (!previousStopId.isEmpty() && stopTimeUpdate.hasStopId()
        && previousStopId.equals(stopTimeUpdate.getStopId())) {
    ... id + " has repeating stop_id " + previousStopId
        [+ " at stop_sequence " + stopTimeUpdate.getStopSequence()]
}
```

**`isEmpty()` is doing the work `hasStopId()` does for the other operand.**
`:112` assigns the unguarded getter, so a stop_time_update with no stop_id
leaves `""` behind; without the emptiness test two consecutive bare
stop_time_updates would report. A feed that sends `stop_id` explicitly set to
the empty string is indistinguishable from one that omits it here, which is
upstream's behaviour and not a simplification made in this port.

**The `at stop_sequence` clause is conditional on the second stop_time_update.**
Upstream builds the prefix with a `StringBuilder` and appends the clause only
under `hasStopSequence()`, so one feed can produce both shapes of text.

Entity order, stop_time_update order.
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

RULE_ID = "E037"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One per adjacent pair the shared walk found repeating a stop_id."""
    return occurrences_for(RULE_ID, message, ctx)
