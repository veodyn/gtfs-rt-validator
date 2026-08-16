"""W004: a VehiclePosition reporting a speed no vehicle plausibly has.

Ported from `validation/rules/VehicleValidator.java:96-104` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`:

```java
if (v.hasPosition() && v.getPosition().hasSpeed()) {
    if (v.getPosition().getSpeed() > MAX_REALISTIC_SPEED_METERS_PER_SECOND ||
            v.getPosition().getSpeed() < 0f) {
        String prefix = getVehicleId(entity, v) + " speed of " + v.getPosition().getSpeed()
            + " m/s (" + String.format("%.2f", GtfsUtils.toMilesPerHour(v.getPosition().getSpeed()))
            + " mph)";
        RuleUtils.addOccurrence(W004, prefix, w004List, _log);
    }
}
```

`MAX_REALISTIC_SPEED_METERS_PER_SECOND` is `26.0f` (`:57`), roughly 60 mph. Both
bounds are strict, so exactly 26.0 and exactly 0.0 pass; 26.0 is exactly
representable, so that boundary is not a rounding question. A negative speed is
reported rather than taken as a direction, which is the second half of the
condition and the reason the rule catches sign errors as well as magnitude ones.

**Three renderings here, none of them Python's default.** The raw speed is a
proto float concatenated by Java, so it goes through `Float.toString` as JDK 17
writes it. The mph figure is `toMilesPerHour`, a *float* multiply by `2.23694f`
rather than a double one, formatted with `String.format("%.2f", ...)`, which is
HALF_UP over the shortest decimal digits and not Python's banker's rounding.
That `String.format` takes no `Locale`, so its decimal separator follows the
JVM's default; a jar run under a comma-decimal locale writes different bytes
here, and that is upstream's behaviour rather than a defect. All three live in
`_shared/javafmt.py` and `_shared/positions.py`.

This check sits before the position block and outside it, so a vehicle can
report an unrealistic speed and an invalid position in one entity. See
`_shared/walk_vehicle.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.walk_vehicle import vehicles
from gtfs_rt_validator.rules._shared.walks import events_for
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "W004"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """This rule's share of the one `VehicleValidator` pass, in entity order."""
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, vehicles, message, ctx)
    ]
