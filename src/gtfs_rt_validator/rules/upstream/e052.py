"""E052: two VehiclePositions in one message claiming the same vehicle.id.

Ported from `validation/rules/VehicleValidator.java:84-94` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`:

```java
HashSet<String> vehicleIds = new HashSet<>(entityList.size());       // :70
...
if (StringUtils.isEmpty(v.getVehicle().getId())) {                   // W002
} else {
    if (vehicleIds.contains(v.getVehicle().getId())) {
        RuleUtils.addOccurrence(E052, "entity ID " + entity.getId()
            + " has vehicle.id " + v.getVehicle().getId(), e052List, _log);
    } else {
        vehicleIds.add(v.getVehicle().getId());
    }
}
```

Three consequences worth stating, because each is a way a port goes wrong:

- **The set is per message, not per entity**, so this is the one rule in the
  validator that needs state carried across the loop. It lives in
  `_shared/walk_vehicle.py`, where the loop is.
- **The first copy is the one that is not reported.** The set is tested before
  the id is added, so n copies of an id give n-1 occurrences, and the entity
  named in each is the later one.
- **A blank vehicle.id is never a duplicate.** This is the `else` of the W002
  test, so the set never sees an empty id however many entities carry one.

VehiclePositions only: `:84-94` is inside `if (entity.hasVehicle())`, so a
TripUpdate naming the same vehicle contributes nothing.

`vehicle.id` in the text has a dot, matching every other identifier upstream
writes for a VehicleDescriptor, though this site builds the string inline
rather than calling `GtfsUtils`.
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

RULE_ID = "E052"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """This rule's share of the one `VehicleValidator` pass, in entity order."""
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, vehicles, message, ctx)
    ]
