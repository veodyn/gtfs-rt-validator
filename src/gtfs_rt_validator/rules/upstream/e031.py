"""E031: an alert's route_id that its own trip's route_id contradicts.

`checkE031` in `validation/rules/TripDescriptorValidator.java:371-378`. Reads no
static data at all: both sides of the comparison come off the wire, which is
what separates it from E030 sitting behind the same gate at `:185`. That gate
needs the selector to have a route_id *and* a trip, and this body needs the trip
to have a route_id too.

The manifest's suffix for it, `"- routes_ids must be the same"`, carries
upstream's own typo and is reproduced rather than corrected.

The prefix is `"alert ID " + entity.getId() + " informed_entity.route_id " +
routeId + " does not equal informed_entity.trip.route_id " +
entitySelector.getTrip().getRouteId()`.
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

RULE_ID = "E031"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
