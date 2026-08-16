"""E036: two stop_time_updates in a row carry the same stop_sequence.

Ported from `validation/rules/StopTimeUpdateValidator.java:251-257`, called from
the walk at `:105-107` whenever a previous value exists:

```java
if (stopTimeUpdate.hasStopSequence() && previousStopSequence == stopTimeUpdate.getStopSequence()) {
    String id = GtfsUtils.getTripId(entity, entity.getTripUpdate());
    RuleUtils.addOccurrence(E036, id + " has repeating stop_sequence " + previousStopSequence, ...);
}
```

**The comparison is numeric.** `previousStopSequence` is an `Integer` and
`getStopSequence()` an `int`, so Java unboxes rather than comparing references.
Values above 127 would otherwise fall outside the `Integer` cache and stop
matching, which is exactly the kind of accident this note exists to rule out.

**An absent stop_sequence stores 0.** `:111` assigns the *unguarded* getter, so
a stop_time_update with no stop_sequence leaves 0 behind, and an explicit
stop_sequence 0 immediately after it fires this rule. That asymmetry with the
guarded append two lines later is a property of the shared walk, which is why
this rule cannot loop on its own.

The prefix re-fetches the TripUpdate off the entity rather than using the
parameter its caller already has; same object, ported as written.

Entity order, stop_time_update order, and three identical stop_sequences in a
row give two occurrences.
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

RULE_ID = "E036"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One per adjacent pair the shared walk found repeating a stop_sequence."""
    return occurrences_for(RULE_ID, message, ctx)
