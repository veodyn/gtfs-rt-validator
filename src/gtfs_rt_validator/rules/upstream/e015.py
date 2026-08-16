"""E015: a stop_id referenced by the realtime feed whose location_type is not 0.

Ported from `validation/rules/StopValidator.java:53-101` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. Two sites, both guarded by
`hasStopId()`: a TripUpdate's stop_time_updates (`:65-69`) and a
VehiclePosition's own stop_id (`:81-86`).

**Alerts are exempt.** The alert branch (`:90-100`) has an E011 site and no
E015 site, and upstream's own `StopValidatorTest.testE015` pins that: its
fourth stage adds an informed_entity naming a location_type 1 stop and still
expects 2, with the comment "Alerts can reference location_types other than 0."

**The null guard is dead in practice.** The Java is:

```java
Integer locationType = gtfsMetadata.getStopToLocationTypeMap().get(stopId);
if (locationType != null && locationType != 0) { fire }
```

onebusaway's `Stop.locationType` is a primitive `int` defaulting to 0, contrary
to the comment on the field in upstream's own source, so the map holds a value
for every stop it holds at all. The `!= null` half therefore only fires for a
stop_id absent from the map entirely, which is E011's case, and reporting it
here as well would double-count the same reference. `static/context.py` records
the same finding against `GtfsMetadata.java:219-232`, and `.get(stop_id)`
returning `None` below is that guard, kept rather than collapsed so the Java
reads across one for one.

**The bare stop_id, never `agencyId + "_" + id`.** The compound form is what
`validation/gtfs/StopLocationTypeValidator.java` keys on for E010, which
`BatchProcessor` never registers and this project therefore never emits;
`StopValidator` keys on `getStopId()` off the wire. Under the compound spelling
this rule would find nothing in `stop_location_types` and silently report
nothing at all. `e011.py` carries the same note.

The occurrence text is shared with E011 and lives in `rules/_shared/stops.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.stops import trip_update_prefix, vehicle_prefix
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "E015"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """One pass over the entities, two branches per entity in the Java's order."""
    location_types = ctx.static.stop_location_types
    for entity in message.get("entity"):
        if entity.has("trip_update"):
            trip_update = entity.get("trip_update")
            for stop_time_update in trip_update.get("stop_time_update"):
                if stop_time_update.has("stop_id"):
                    stop_id = stop_time_update.get("stop_id")
                    if _misplaced(location_types.get(stop_id)):
                        yield Occurrence(RULE_ID, trip_update_prefix(trip_update, stop_id))
        if entity.has("vehicle"):
            position = entity.get("vehicle")
            if position.has("stop_id"):
                stop_id = position.get("stop_id")
                if _misplaced(location_types.get(stop_id)):
                    yield Occurrence(RULE_ID, vehicle_prefix(position, stop_id))


def _misplaced(location_type: int | None) -> bool:
    """`locationType != null && locationType != 0`, both halves. See the docstring."""
    return location_type is not None and location_type != 0
