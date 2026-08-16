"""E030: an alert trip_id that does not belong to the alert's route_id.

`checkE030` in `validation/rules/TripDescriptorValidator.java:350-361`, called
once per `informed_entity` and only when that selector has **both** a route_id
and a trip (`:185`). It shares that gate with E031, so a selector carrying a
trip but no route_id reaches neither.

The `routeId` compared is the **selector's**, `entitySelector.getRouteId()`, not
`informed_entity.trip.route_id`; comparing those two against each other is
E031's job. A trip_id that is in no `trips.txt` row returns without reporting,
which is E003's finding rather than this one's.

The prefix names all three ids and closes with the GTFS answer in parentheses:
`"alert ID " + entity.getId() + " informed_entity.trip.trip_id " + tripId +
" does not belong to informed_entity.route_id " + routeId +
" (GTFS says it belongs to route_id " + gtfsRouteId + ")"`.
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

RULE_ID = "E030"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
