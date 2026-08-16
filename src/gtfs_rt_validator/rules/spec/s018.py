"""S018: a route-scoped TripUpdate whose stop_time_updates name no stop.

The `TripDescriptor` message comment at `:797` describes two ways to write a
descriptor, and the second one carries this obligation:

    Note that if the trip_id is not known, then stop sequence ids in TripUpdate
    are not sufficient, and stop_ids must be provided as well.

A `stop_sequence` is an index into one trip's `stop_times.txt` rows. With no
trip_id there is no such row set, so the number resolves to nothing and a
consumer holding the update cannot say which stop it predicts for. The proto's
answer is that the route-scoped form has to spell the stop out.

**Not E040, and the two are disjoint by construction.** E040 fires for a
stop_time_update carrying neither `stop_id` nor `stop_sequence`, accepting
either. This rule's band is the one E040 accepts and the proto does not:
`stop_sequence` alone on a trip nothing can resolve. A fixture whose only defect
is this one leaves the jar silent, which is the empirical form of that claim and
is asserted in `tests/test_spec_tier_does_not_shadow_the_jar.py`. W006 is the
other neighbour and stops at reporting the absent trip_id.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import relationships
from gtfs_rt_validator.rules._shared.trip_descriptor_spec import route_scoped, route_text
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S018"

CLAUSE = (
    "spec: Note that if the trip_id is not known, then stop sequence ids in TripUpdate "
    "are not sufficient, and stop_ids must be provided as well."
)


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"{route_text(found.trip)} stop_time_update[{stop.index}] has no stop_id",
            {ENTITY_PATH_KEY: stop.path},
        )
        for found in relationships(message, ctx)
        if found.payload == "trip_update" and route_scoped(found.trip)
        for stop in found.stop_time_updates
        if not stop.update.has("stop_id")
    ]
