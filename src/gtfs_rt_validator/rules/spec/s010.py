"""S010: a stop_time_update that is not UNSCHEDULED under a trip that is.

`:859`, in `TripDescriptor.ScheduleRelationship.UNSCHEDULED`'s comment. S009 is
the other direction, cited from `:260` on the stop_time_update enum, and the two
are separate rules for the reason S009's docstring gives.

**One occurrence per offending update**, where S009 reports once per trip. The
sentence here says "all StopTimeUpdates", so the defect is each update that is
not, and an occurrence that did not name which one would leave the producer to
find it.

The value compared is the resolved one, so an update that declares nothing is
SCHEDULED and is reported: under an UNSCHEDULED trip, omitting the field is
exactly the mistake, since the proto2 default is the value the clause forbids.
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

RULE_ID = "S010"

CLAUSE = (
    "Trips with ScheduleRelationship=UNSCHEDULED must also set all "
    "StopTimeUpdates.ScheduleRelationship=UNSCHEDULED."
)

NOT_UNSCHEDULED = (
    "trip_id {trip_id} stop_time_update[{index}] is {relationship} on an UNSCHEDULED trip"
)


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per update that did not follow its UNSCHEDULED descriptor."""
    return [
        found
        for record in relationships(message, ctx)
        if record.payload == "trip_update" and record.relationship == UNSCHEDULED
        for found in _of_trip(record)
    ]


def _of_trip(record: TripRelationship) -> list[Occurrence]:
    trip_id = record.trip.get("trip_id")
    return [
        Occurrence(
            RULE_ID,
            NOT_UNSCHEDULED.format(
                trip_id=trip_id, index=stop_time.index, relationship=stop_time.relationship
            ),
            {
                ENTITY_PATH_KEY: stop_time.path,
                "tripId": trip_id,
                "scheduleRelationship": stop_time.relationship,
            },
        )
        for stop_time in record.stop_time_updates
        if stop_time.relationship != STOP_TIME_UNSCHEDULED
    ]
