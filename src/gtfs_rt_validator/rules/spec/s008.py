"""S008: an UNSCHEDULED stop_time_update on a trip that is not frequency-based.

`:259`, in the `UNSCHEDULED` member's own comment, and a WARNING because the
sentence says `should`. The mirror of S007 and a different clause: `:242` says
which trips ought to use the value, this one says which may not.

Both halves of the sentence are one predicate. "trips that are not defined in
GTFS frequencies.txt" and "trips in GTFS frequencies.txt with exact_times = 1"
are the two ways of being outside `exact_times_zero_trip_ids`, which
`GtfsMetadata` builds from the rows where `exact_times` is 0 or blank.

**A descriptor with no `trip_id` says nothing here.** There is no row to decide
against, so the rule that fires on the missing trip_id is W006 and this one
stays quiet rather than treating the empty string as a trip absent from
`frequencies.txt`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import (
    STOP_TIME_UNSCHEDULED,
    relationships,
)
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S008"

CLAUSE = (
    "This value should not be used for trips that are not defined in GTFS frequencies.txt, "
    "or trips in GTFS frequencies.txt with exact_times = 1."
)

UNSCHEDULED_OFF_FREQUENCY = (
    "trip_id {trip_id} stop_time_update[{index}] is UNSCHEDULED on a trip that is not exact_times=0"
)


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per UNSCHEDULED update of a trip outside the frequency set."""
    frequency_trips = ctx.static.exact_times_zero_trip_ids
    return [
        found
        for record in relationships(message, ctx)
        if record.payload == "trip_update"
        and record.trip.has("trip_id")
        and record.trip.get("trip_id") not in frequency_trips
        for found in _of_trip(record)
    ]


def _of_trip(record: TripRelationship) -> list[Occurrence]:
    trip_id = record.trip.get("trip_id")
    return [
        Occurrence(
            RULE_ID,
            UNSCHEDULED_OFF_FREQUENCY.format(trip_id=trip_id, index=stop_time.index),
            {ENTITY_PATH_KEY: stop_time.path, "tripId": trip_id},
        )
        for stop_time in record.stop_time_updates
        if stop_time.relationship == STOP_TIME_UNSCHEDULED
    ]
