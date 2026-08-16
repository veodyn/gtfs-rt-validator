"""E004: a realtime route_id that GTFS `routes.txt` does not have.

`checkE004` in `validation/rules/TripDescriptorValidator.java:259-264`, called
unconditionally for every TripUpdate (`:123`) and for every VehiclePosition that
has a trip (`:171`). **Never for an alert.** `checkE004` has exactly those two
call sites, so `informed_entity.route_id` and `informed_entity.trip.route_id` go
unchecked by this rule; nobody found a comment explaining why, and compat must
not add the call.

There is no `hasRouteId()` test here. `StringUtils.isEmpty(routeId)` does that
work, which makes an absent route_id and one set to the empty string the same
thing, unlike E035's `hasRouteId()` a few methods down.

The prefix is `GtfsUtils.getVehicleAndRouteId(entity)`: `route_id X` for a
TripUpdate and `vehicle_id V route_id X` for a VehiclePosition. Both chain
through unguarded getters, so a VehiclePosition carrying no vehicle descriptor
gives `vehicle_id  route_id X`, double space included.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.walk_trip_descriptor import trip_descriptors
from gtfs_rt_validator.rules._shared.walks import events_for
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "E004"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
