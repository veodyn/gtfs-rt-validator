"""W009: a TripDescriptor or stop_time_update with no schedule_relationship.

Two overloads in `validation/rules/TripDescriptorValidator.java`. The
TripDescriptor one (`:470-474`) fires on `!hasScheduleRelationship()` and is
called for the TripUpdate trip (`:139`), the VehiclePosition trip (`:175`) and
every alert informed_entity trip (`:191`); its prefix is
`GtfsUtils.getTripId(entity, tripDescriptor)`, so `trip_id X` or `entity ID Y`.
The stop_time_update one (`:483-487`) fires on the same test and reads the trip
half of its prefix off `entity.getTripUpdate().getTrip()` rather than off
anything handed to it, closing with `" (and potentially more for this trip)"`.

Inside one TripUpdate the stop_time_update warnings come **before** the
trip-level one (`:129-140`).

**The suppression list is whole-feed, and reproducing that is the requirement.**
`errorListW009` is created once per `validate` call and never reset per entity,
while `foundW009` is per TripUpdate:

    boolean foundW009 = false;
    for (StopTimeUpdate stu : tripUpdate.getStopTimeUpdateList()) {
        if (!foundW009) {
            checkW009(entity, stu, errorListW009);
            if (!errorListW009.isEmpty()) foundW009 = true;
        }
    }

So once any W009 exists anywhere in the feed, including one from an earlier
entity's TripDescriptor, the first stop_time_update of every later TripUpdate
flips the flag whether or not it added anything, and that trip's remaining
stop_time_updates are never examined. The intended "one per trip" cap degrades
to "one check per trip after the first W009 anywhere". A port with a per-trip
list emits strictly more occurrences than the jar; the list lives in
`_shared/walk_trip_descriptor.py` for that reason.

**The enum gap fires this rule.** `hasScheduleRelationship()` is false for a
post-2015 value under the 2015 schema, so a trip declaring DUPLICATED is warned
about as though the field were absent.
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

RULE_ID = "W009"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
