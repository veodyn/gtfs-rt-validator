"""E009: no stop_sequence on a trip that visits one stop_id more than once.

Ported from `validation/rules/StopTimeUpdateValidator.java:99-104`, at the top
of the stop_time_update loop:

```java
if (!foundE009error && tripId != null && tripWithMultiStop.containsKey(tripId)
        && !stopTimeUpdate.hasStopSequence()) {
    List<String> stopIds = tripWithMultiStop.get(tripId);
    RuleUtils.addOccurrence(E009,
        "trip_id " + tripId + " visits stop_id " + stopIds.toString(), e009List, _log);
    foundE009error = true;  // Only log error once for this trip
}
```

**`foundE009error` is per entity, not per trip_id.** It is declared at `:94`,
inside the `for (FeedEntity entity : entityList)` body, so two TripUpdate
entities naming the same trip_id each report once. Upstream's own comment says
"for this trip" and is loose about the difference; the declaration is where the
answer is, and `tests/test_rule_e009.py` pins it.

**The prefix names every repeat visit, not every visited stop.**
`getTripsWithMultiStops` (`GtfsMetadata.java:196-213`) collects a stop_id the
second time it is seen on a trip, so a stop visited three times contributes two
entries. `List.toString()` renders that `[222]` or `[222, 230]`: square
brackets, comma and space, no quotes, which `_shared/javafmt.java_list`
reproduces and Python's own `str(list)` does not.

The rule reads `trips_with_multi_stops`, and only a trip present in it can fire.
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

RULE_ID = "E009"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """At most one per TripUpdate entity, on its first bare stop_time_update."""
    return occurrences_for(RULE_ID, message, ctx)
