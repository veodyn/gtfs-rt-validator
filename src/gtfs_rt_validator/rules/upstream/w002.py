"""W002: a TripUpdate or a VehiclePosition that names no vehicle_id.

Ported from `validation/rules/VehicleValidator.java:73-86` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. Two independent sites per entity,
the TripUpdate one first:

```java
if (StringUtils.isEmpty(tripUpdate.getVehicle().getId()))            // :76
    RuleUtils.addOccurrence(W002, getTripId(entity, tripUpdate), ...);
if (StringUtils.isEmpty(v.getVehicle().getId()))                     // :84
    RuleUtils.addOccurrence(W002, "entity ID " + entity.getId(), ...);
```

Neither has a `hasVehicle()` guard, and neither needs one: `getVehicle()` on a
message with no VehicleDescriptor answers the default instance, whose `getId()`
is `""`, which `StringUtils.isEmpty` calls empty. So "no descriptor at all" and
"a descriptor with a blank id" are the same finding, which is the rule.

**The two halves do not share a helper, and their prefixes differ in shape.**
The TripUpdate half calls `getTripId(entity, tripUpdate)`, so it reads
`trip_id X` or falls back to `entity ID Y`; the VehiclePosition half writes
`"entity ID " + entity.getId()` inline and has no vehicle or trip form at all.
That asymmetry is upstream's, and it is visible in one entity carrying both.

The VehiclePosition site is also E052's gate: E052 is the `else` of `:84`, so a
blank vehicle.id is this warning and is never a duplicate. See
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

RULE_ID = "W002"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """This rule's share of the one `VehicleValidator` pass, in entity order."""
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, vehicles, message, ctx)
    ]
