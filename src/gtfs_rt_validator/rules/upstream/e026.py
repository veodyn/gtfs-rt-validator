"""E026: a VehiclePosition whose coordinates are missing or not WGS84.

Ported from `validation/rules/VehicleValidator.java:109-114` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. Two mutually exclusive branches
inside `if (v.hasPosition())`, tested in this order:

```java
if (!position.hasLatitude() || !position.hasLongitude()) {
    RuleUtils.addOccurrence(E026, id + " position is missing lat/long", ...);
} else if (!GtfsUtils.isPositionValid(position)) {
    RuleUtils.addOccurrence(E026, id + " has latitude/longitude of ("
        + position.getLatitude() + "," + position.getLongitude() + ")", ...);
}
```

So at most one occurrence per VehiclePosition, and none at all for a vehicle
that reports no position. `isPositionValid` is in `_shared/positions.py`: its
bounds are inclusive at -90, 90, -180 and 180, and it reads both coordinates
with no presence guard, which is safe here only because the branch above has
already established both are set.

**The first branch is unreachable from feed bytes.** `Position.latitude` and
`.longitude` are `required` in the 2015 proto and in the current one alike, so
`isInitialized` fails and protobuf-java, like `proto/decode.py`, refuses the
whole message before any rule sees it; upstream skips the file. It is ported
because the Java tests it first, and `tests/test_rule_e026.py` pins both the
refusal and the branch.

The coordinates reach output through `Float.toString`, not `repr`, and there is
no space after the comma. Which rule sees which position, and why an invalid
one never reaches E028 or E029, is `_shared/walk_vehicle.py`.
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

RULE_ID = "E026"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """This rule's share of the one `VehicleValidator` pass, in entity order."""
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, vehicles, message, ctx)
    ]
