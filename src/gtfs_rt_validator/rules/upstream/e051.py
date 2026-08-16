"""E051: a stop_sequence no `stop_times.txt` row of this trip carries.

Ported from `validation/rules/StopTimeUpdateValidator.java:173-181`, after the
four per-stop_time_update checks:

```java
if (unknownRtStopSequence) {
    RuleUtils.addOccurrence(E051, "GTFS-rt " + GtfsUtils.getTripId(entity, tripUpdate)
        + " contains stop_sequence " + stopTimeUpdate.getStopSequence(), e051List, _log);
    break;   // skip the rest of this trip's stop_time_updates
}
```

**The `break` is the reason `_shared/walk_stop_time_updates.py` exists.** It
abandons the rest of that TripUpdate for *every* rule in the validator, not only
for this one: no E036, E037, E040, E042, E043, E044, E045 or E046 for the
stop_time_updates after it, their stop_sequences never reach E002's list, and
E002's verdict is computed from what is left. Upstream's comment at `:176-179`
says why: keeping the whole validator at O(n + m) rather than rescanning
`stop_times.txt` per stop_time_update. A rule looping on its own would report
findings the jar never reaches, which is why none of the twelve does.

**The flag is only ever set on the last GTFS row.** `:148-151` sets it when the
index has just passed the end of `stop_times.txt` without matching, so a bad
stop_sequence in the middle of a trip is not detected where it sits: the walk
consumes every remaining row first. Only the reported stop_sequence says which
one was wrong, and a wrong stop_sequence 0 in the *first* stop_time_update
therefore costs the whole trip.

At most one occurrence per TripUpdate, always for the first offending
stop_time_update. The offending one is itself still fully checked, because the
`break` comes after `:168-171`.
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

RULE_ID = "E051"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """At most one per TripUpdate, where the shared walk ran out of GTFS rows."""
    return occurrences_for(RULE_ID, message, ctx)
