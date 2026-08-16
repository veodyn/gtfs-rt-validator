"""E035: a realtime trip_id that does not belong to its realtime route_id.

`checkE035` in `validation/rules/TripDescriptorValidator.java:432-448`, and the
only check in this validator called from **all three** halves of the dispatch:
the TripUpdate trip (`:125`), the VehiclePosition trip (`:174`) and every alert
informed_entity's trip (`:184`). One entity carrying all three with the same bad
descriptor therefore produces three occurrences, which is exactly what upstream's
own `testE035` counts.

The alert-side call is **unconditional**, outside the `hasTrip()` guard that
wraps W006 and W009, so a selector with no trip hands it the default
TripDescriptor and the `hasTripId()` test inside short-circuits.

Both early returns defer to another rule rather than duplicating it: a route_id
that is in no `routes.txt` row is E004's finding, and a trip_id in no
`trips.txt` row is E003's. So this rule reports only when both ids exist and
GTFS puts the trip on a different route.

The prefix is `"GTFS-rt entity ID " + entity.getId() + " trip_id " + tripId +
" has route_id " + routeId + " but belongs to GTFS route_id " + gtfsRouteId`,
and it names the FeedEntity's id rather than any trip text helper.
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

RULE_ID = "E035"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
