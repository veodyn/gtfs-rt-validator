"""E006: a frequency-based exact_times = 0 trip with no start_date or no start_time.

Ported from `validation/rules/FrequencyTypeZeroValidator.java:51-111` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. Four sites, two per half of an
entity, and each half tests the two fields independently rather than as an
if/else, so a descriptor missing both reports twice on that side:

```java
if (!tripUpdate.getTrip().hasStartDate())  -> "trip_id X is missing start_date"
if (!tripUpdate.getTrip().hasStartTime())  -> "trip_id X is missing start_time"
```

**The two halves spell the prefix differently**, and `_shared/frequencies.py`
holds both forms. The TripUpdate half (`:61`, `:66`) names the trip alone; the
VehiclePosition half (`:91`, `:96`) puts the vehicle first, reading
`vehiclePosition.getVehicle().getId()` with no guard, so
an absent VehicleDescriptor gives `"vehicle_id  trip_id 1 is missing
start_date"` with a double space. Measured: that is what the pinned jar wrote
for a feed with no descriptor on the VehiclePosition.

**Neither field's *format* is E006's business.** Upstream's own test walks
through `start_date = "4-24-2016"` and `start_time = "08:00:00AM"`, neither of
which is valid GTFS, and expects the count to fall to zero: E021 and E020 are
the rules that read them. `hasStartDate()` and `hasStartTime()` are presence,
nothing more.

The gate, and the reason the two halves are guarded differently, is in
`rules/_shared/frequencies.py` with the entity walk.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.frequencies import frequency_zero_halves, half_id_text
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "E006"

#: The two fields, in the order the Java tests them.
REQUIRED = ("start_date", "start_time")


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """start_date then start_time, per half, in the Java's order."""
    for _entity, half in frequency_zero_halves(message, ctx.static.exact_times_zero_trip_ids):
        trip = half.get("trip")
        prefix = half_id_text(half)
        for field in REQUIRED:
            if not trip.has(field):
                yield Occurrence(RULE_ID, f"{prefix} is missing {field}")
