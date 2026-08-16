"""W005: a frequency-based exact_times = 0 trip with no vehicle_id.

Ported from `validation/rules/FrequencyTypeZeroValidator.java:74` and `:105` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. One site per half of an entity, and
the two halves ask different questions and answer in unrelated text.

```java
if (!tripUpdate.hasVehicle() || !tripUpdate.getVehicle().hasId())   // :74
    -> "trip_id " + tripUpdate.getTrip().getTripId()

if (!vehiclePosition.getVehicle().hasId())                          // :105
    -> "entity ID" + entity.getId() + "with trip_id " + vehiclePosition.getTrip().getTripId()
```

**Both missing spaces in the second one are in the source**, so the jar writes
`entity IDTEST_ENTITYwith trip_id 1`. Measured, not read: that is what came back
from the pinned jar for an entity with `id = "TEST_ENTITY"`. Reproduced rather
than corrected, because under `--compat` the bytes are the contract.

The VehiclePosition half has no `hasVehicle()` disjunct, which changes nothing:
`getVehicle()` on an absent field returns the default instance and `hasId()` on
that is false, so a VehiclePosition with no descriptor at all still reports. The
test is `hasId()` throughout, so a descriptor carrying only a label reports too.

The gate, and the reason the two halves are guarded differently, is in
`rules/_shared/frequencies.py` with the entity walk.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.frequencies import (
    TRIP_UPDATE,
    frequency_zero_halves,
    trip_id_text,
)
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "W005"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per half that names no vehicle id, in the Java's order."""
    for entity, half in frequency_zero_halves(message, ctx.static.exact_times_zero_trip_ids):
        if half.desc.name == TRIP_UPDATE:
            if not half.has("vehicle") or not half.get("vehicle").has("id"):
                yield Occurrence(RULE_ID, trip_id_text(half))
        elif not half.get("vehicle").has("id"):
            yield Occurrence(RULE_ID, _vehicle_prefix(entity, half))


def _vehicle_prefix(entity: Msg, position: Msg) -> str:
    """`:107` exactly, including the two spaces that are not in it."""
    trip_id = position.get("trip").get("trip_id")
    return f"entity ID{entity.get('id')}with trip_id {trip_id}"
