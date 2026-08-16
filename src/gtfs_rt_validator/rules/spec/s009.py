"""S009: UNSCHEDULED stop_time_updates under a descriptor that is not.

`:260`, in the `UNSCHEDULED` member's comment on the stop_time_update enum.
S010 is the other direction, cited from `:859` on the trip enum, and they are
two rules rather than one because they fire on different feeds and quote
different sentences at different lines. A single rule would have to pick one
citation and lie about the other, which is exactly what the citation gate
exists to prevent.

They also cannot both fire on one trip: this one needs a descriptor that is not
UNSCHEDULED and S010 needs one that is.

**One occurrence per trip.** The defect the sentence names is the descriptor's,
so a trip with forty UNSCHEDULED updates has one wrong descriptor rather than
forty wrong updates. S010 counts the other way for the same reason: there the
defect is the update's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import (
    STOP_TIME_UNSCHEDULED,
    UNSCHEDULED,
    relationships,
)
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S009"

CLAUSE = (
    "Trips containing StopTimeUpdates with ScheduleRelationship=UNSCHEDULED must also set "
    "TripDescriptor.ScheduleRelationship=UNSCHEDULED."
)

MISMATCHED = "trip_id {trip_id} has UNSCHEDULED stop_time_updates but the trip is {relationship}"


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per trip whose descriptor did not follow its updates."""
    return [
        _found(record)
        for record in relationships(message, ctx)
        if record.payload == "trip_update"
        and record.relationship != UNSCHEDULED
        and any(
            stop_time.relationship == STOP_TIME_UNSCHEDULED
            for stop_time in record.stop_time_updates
        )
    ]


def _found(record: TripRelationship) -> Occurrence:
    trip_id = record.trip.get("trip_id")
    return Occurrence(
        RULE_ID,
        MISMATCHED.format(trip_id=trip_id, relationship=record.relationship),
        {
            ENTITY_PATH_KEY: record.path,
            "tripId": trip_id,
            "scheduleRelationship": record.relationship,
        },
    )
