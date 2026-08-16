"""E046: a time-less arrival or departure over a GTFS row that has no time either.

Ported from `validation/rules/StopTimeUpdateValidator.java:424-440`:

```java
if (stopTimeUpdate.hasArrival()) {
    if (!stopTimeUpdate.getArrival().hasTime() && !gtfsStopTime.isArrivalTimeSet()) { ... "arrival.time" }
}
if (stopTimeUpdate.hasDeparture()) {
    if (!stopTimeUpdate.getDeparture().hasTime() && !gtfsStopTime.isDepartureTimeSet()) { ... "departure.time" }
}
```

**Neither condition tests `hasDelay()`.** This rule is easily read as "the
producer sent only a delay", and those two lines say no such thing: a
`StopTimeEvent` carrying *nothing at all* reports here too, alongside its E044.
Read the Java before narrowing this.

`isArrivalTimeSet()` in onebusaway-gtfs 1.3.87 is `arrivalTime != -999`
(`StopTime.java:30, 191-195`), the sentinel for a blank cell. The sibling's
loader gives `None` for that same blank, so the walk asks
`row["arrival_time"] is None`.

**Two call sites, both inside the walk's `while` loop, never both for one
stop_time_update.** On a stop_sequence match at `:130`, with the matched row; or
on a stop_id match when the feed sent no stop_sequence at all, at `:160`, with
`gtfsStopTimes.get(gtfsStopTimeIndex - 1)`. The `- 1` is not an off-by-one:
`:143` already incremented, so it is the row whose stop_id matched. When the
feed *does* send a stop_sequence the second site is dead, gated on
`!stu.hasStopSequence()`; when the stop_sequence matches nothing, or the trip is
absent from `stop_times.txt`, neither site is reached and this rule cannot fire
however blank the static feed is.
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

RULE_ID = "E046"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """Up to two per GTFS row the shared walk matched a stop_time_update to."""
    return occurrences_for(RULE_ID, message, ctx)
