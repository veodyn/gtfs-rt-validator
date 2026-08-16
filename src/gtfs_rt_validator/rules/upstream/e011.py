"""E011: a stop_id referenced by the realtime feed that GTFS stops.txt does not have.

Ported from `validation/rules/StopValidator.java:53-101` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. Three sites, each guarded by
`hasStopId()`, each testing `!gtfsMetadata.getStopIds().contains(stopId)`: a
TripUpdate's stop_time_updates (`:59-64`), a VehiclePosition's own stop_id
(`:75-80`), and an alert's informed_entities (`:92-97`). E015 is the other rule
in this validator and it exempts alerts, which is why only this one has a third
branch.

**The bare stop_id, never `agencyId + "_" + id`.** The compound form belongs to
`validation/gtfs/StopLocationTypeValidator.java`, whose body reads
`stopTime.getStop().getId()`, an onebusaway `AgencyAndId` whose `toString()`
joins the agency to the id with an underscore. That validator emits E010, is a
`GtfsFeedValidator` rather than a `FeedEntityValidator`, and is registered by
neither shipped entry point (`batch/BatchProcessor.java:150-158` lists nine
validators and it is not among them), so E010 has no module in this project at
all and emitting it would itself be a parity failure. `StopValidator` reads
`getStopId()` off the wire and looks that string up unchanged.

**No de-duplication.** `StopLocationTypeValidator` keeps a `checkedStops` set;
this validator keeps none, so a trip naming the same missing stop twice reports
twice.

The occurrence text, and the three details in it that look like typos, live in
`rules/_shared/stops.py` with the reasons.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.stops import (
    alert_prefix,
    trip_update_prefix,
    vehicle_prefix,
)
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "E011"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """One pass over the entities, three branches per entity in the Java's order."""
    known = ctx.static.stop_ids
    for entity in message.get("entity"):
        if entity.has("trip_update"):
            trip_update = entity.get("trip_update")
            for stop_time_update in trip_update.get("stop_time_update"):
                if stop_time_update.has("stop_id"):
                    stop_id = stop_time_update.get("stop_id")
                    if stop_id not in known:
                        yield Occurrence(RULE_ID, trip_update_prefix(trip_update, stop_id))
        if entity.has("vehicle"):
            position = entity.get("vehicle")
            if position.has("stop_id"):
                stop_id = position.get("stop_id")
                if stop_id not in known:
                    yield Occurrence(RULE_ID, vehicle_prefix(position, stop_id))
        if entity.has("alert"):
            for selector in entity.get("alert").get("informed_entity"):
                if selector.has("stop_id"):
                    stop_id = selector.get("stop_id")
                    if stop_id not in known:
                        yield Occurrence(RULE_ID, alert_prefix(entity, stop_id))
