"""E027: a VehiclePosition reporting a bearing outside 0 to 360 degrees.

Ported from `validation/rules/VehicleValidator.java:123-126` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`:

```java
if (!GtfsUtils.isBearingValid(position)) {
    RuleUtils.addOccurrence(E027, id + " has bearing of " + position.getBearing(), ...);
}
```

Two things about where that sits. It requires `v.hasPosition()`, so a vehicle
reporting no position at all is never checked, and it is a **sibling** of the
E026 if/else rather than a branch of it, so a position with impossible
coordinates and an impossible bearing reports both. That placement is the
walk's, in `_shared/walk_vehicle.py`.

`isBearingValid` is in `_shared/positions.py` and starts with
`if (!position.hasBearing()) return true`, so an absent bearing is valid rather
than being compared against the proto default of 0. Both ends of the range are
inclusive: the comparison is `< 0 || > 360`.

`getBearing()` is a proto float, so it reaches output through `Float.toString`
and an integral bearing prints with a trailing `.0`.
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

RULE_ID = "E027"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """This rule's share of the one `VehicleValidator` pass, in entity order."""
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, vehicles, message, ctx)
    ]
