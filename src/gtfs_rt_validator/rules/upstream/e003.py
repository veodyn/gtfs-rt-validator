"""E003: a realtime trip_id that GTFS `trips.txt` does not have, and is not ADDED.

Inlined into `validation/rules/TripDescriptorValidator.java`'s dispatch rather
than written as a `checkE003`, at `:102-106` for a TripUpdate and `:150-154` for
a VehiclePosition. Both arms are the `trips.get(tripId) == null` branch of the
same `if`, whose `else` is E016.

**The two prefixes differ.** The TripUpdate arm calls
`GtfsUtils.getTripId(entity, tripUpdate)`, so it reads `trip_id X` and falls
back to `entity ID Y`; the VehiclePosition arm builds its text inline
(`:153`) out of `entity.getVehicle().getVehicle().getId()` with no presence
check, so a VehiclePosition with no `vehicle` descriptor gives
`"vehicle_id  trip_id X"`, double space and all. Neither goes through
`getVehicleAndTripIdText`.

**The enum gap reaches this rule.** `GtfsUtils.isAddedTrip` is
`hasScheduleRelationship() && ... == ADDED`, and the 2015 enum has four members
where today's has eight, so a trip declaring a post-2015 value such as
DUPLICATED is not an ADDED trip to the jar and is reported here exactly as a
trip with no schedule_relationship would be. That is what the two-schema
decoder exists for; see `tests/test_two_views.py`.

**The VehiclePosition side skips an empty trip_id** (`:148`) and the TripUpdate
side does not, so a trip_id set to the empty string is looked up in `trips.txt`
from one half only and reported as `"trip_id "`.
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

RULE_ID = "E003"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
