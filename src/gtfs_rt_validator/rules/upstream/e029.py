"""E029: a vehicle position far from the shape of the trip it says it is on.

Ported from `validation/rules/VehicleValidator.java:200-232` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`.

**It runs only when E028 said the vehicle was inside the agency box.** The call
is inside `if (insideBounds)` at `:118-121`, so a vehicle already reported as
outside the coverage area is never measured against a trip shape as well. A
port that evaluated this rule's own condition independently would report every
such vehicle twice, which the jar never does. The nesting is reproduced once,
in `_shared/walk_vehicle.py`, and never inside this module.

Three early returns come before any geometry, and each is a state a real feed
reaches:

1. `!v.hasTrip() || !v.getTrip().hasTripId()`: nothing to look up.
2. `getBufferedTripShape(tripId) == null`: the trip is not in `trips.txt`, or has
   no usable `shape_id`, or there is no shape data at all because the shapes
   gate is shut or `-ignoreShapes` was passed. That last case is why the flag
   disables this rule without saying so anywhere.
3. A DETOUR service alert covering the vehicle's trip_id or route_id, found by
   `hasDetourAlert` scanning every entity of the same message. It matches on
   `informed_entity.trip.route_id`, never on `informed_entity.route_id`.

The buffer is `geometry/buffer.py`'s port of JTS 1.13, applied in raw degrees
with no latitude correction, so the "200 meters" in the message is 200 m
north-south and about `200 * cos(lat)` east-west. That is upstream's behaviour
and reproducing it is the requirement. The checks and the occurrence text live
in `_shared/vehicle_bounds.py`, next to E028's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.walk_vehicle import vehicles
from gtfs_rt_validator.rules._shared.walks import events_for
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "E029"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """This rule's share of the one `VehicleValidator` pass, in entity order."""
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, vehicles, message, ctx)
    ]
