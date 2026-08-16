"""E002: a trip's stop_time_updates are not strictly sorted by stop_sequence.

Ported from `validation/rules/StopTimeUpdateValidator.java:184-198`, which runs
**after** the stop_time_update loop over lists that loop accumulated. It is
therefore a rule about the walk's state rather than about any one
stop_time_update, and `_shared/walk_stop_time_updates.py` is where it lives.

```java
boolean sorted = Ordering.natural().isStrictlyOrdered(rtStopSequenceList);
if (!sorted) { ... " stop_sequence " + rtStopSequenceList ... }
else if (addedStopSequenceFromStopId
         && rtStopSequenceList.size() < rtStopTimeUpdateList.size()) {
    ... " stop_sequence for stop_ids " + rtStopIdList ...
}
```

**Two mutually exclusive forms.** Form A is the plain one: the stop_sequences
the feed supplied, mixed in feed order with any the walk recovered from GTFS by
stop_id match (`:155`), are not strictly increasing. Guava's `isStrictlyOrdered`
means strictly increasing, so a repeated value is unsorted and a list of nought
or one is sorted. Form B fires only when the feed sent no stop_sequences at all
for some stop_time_update and the walk could not recover every one of them from
`stop_times.txt`: the ones it did find cannot vouch for the order of the ones it
did not.

**The list E002 reads can be truncated.** When E051 broke the loop (`:180`), the
stop_time_updates after the offending one never reached either list, while
`rtStopTimeUpdateList.size()` in form B's test is still the full count. Both are
upstream's behaviour and both are reproduced by reading the walk rather than
looping again.

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

RULE_ID = "E002"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """Whatever the shared walk saw after each TripUpdate's loop finished."""
    return occurrences_for(RULE_ID, message, ctx)
