"""W006: a TripDescriptor with no trip_id.

`checkW006` in `validation/rules/TripDescriptorValidator.java:457-461`, called
from three places: a TripUpdate whose trip has no trip_id (`:98`), a
VehiclePosition **that has a trip** with no trip_id (`:145`), and each alert
informed_entity that has a trip with no trip_id (`:190`). A VehiclePosition with
no `trip` at all produces nothing, because the half is gated on
`getVehicle().hasTrip()`; an alert selector with no trip produces nothing for
the same reason.

On the two vehicle-bearing sides this is the `if` arm of the trip lookup, so a
descriptor that reports W006 can reach neither E003, nor E016, nor E023.

Java's `tripDescriptor != null` guard is unreachable through the decoder, where
an absent sub-message reads back as the default instance rather than as nothing.

The prefix is `"entity ID " + entity.getId()` and names no trip, there being no
trip_id to name.
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

RULE_ID = "W006"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
