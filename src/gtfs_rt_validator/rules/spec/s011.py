"""S011: `StopTimeUpdate.stop_id` disagreeing with `assigned_stop_id`.

`:280`. Both fields have to be populated for the clause to have an antecedent,
and the sentence before it is the advice a producer in that position ignored:
"If this field is populated, it is preferred to omit `StopTimeUpdate.stop_id`
and use only `StopTimeUpdate.stop_sequence`". That sentence's only modal grants
a preference, so it is not a rule; this one says `must` and is.

The comparison is between two fields of the feed and never opens the static
feed, which is what separates it from E011 (is `stop_id` in `stops.txt`) and
from S012 (is `assigned_stop_id` in `stops.txt`). All three can fire on one
update and each says something the others do not.

Presence, not truth: a `stop_id` explicitly written as the empty string is
populated, and it does not match a non-empty assigned stop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import relationships
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S011"

CLAUSE = (
    "If `StopTimeProperties.assigned_stop_id` and `StopTimeUpdate.stop_id` are populated, "
    "`StopTimeUpdate.stop_id` must match `assigned_stop_id`."
)

MISMATCHED = (
    "trip_id {trip_id} stop_time_update[{index}] stop_id {stop_id} does not match "
    "assigned_stop_id {assigned}"
)

PROPERTIES = "stop_time_properties"

ASSIGNED = "assigned_stop_id"


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per update whose two stop ids disagree."""
    return [
        found
        for record in relationships(message, ctx)
        if record.payload == "trip_update"
        for found in _of_trip(record)
    ]


def _of_trip(record: TripRelationship) -> list[Occurrence]:
    trip_id = record.trip.get("trip_id")
    found = []
    for stop_time in record.stop_time_updates:
        update = stop_time.update
        properties = update.get(PROPERTIES)
        if not update.has("stop_id") or not properties.has(ASSIGNED):
            continue
        stop_id = update.get("stop_id")
        assigned = properties.get(ASSIGNED)
        if stop_id == assigned:
            continue
        found.append(
            Occurrence(
                RULE_ID,
                MISMATCHED.format(
                    trip_id=trip_id, index=stop_time.index, stop_id=stop_id, assigned=assigned
                ),
                {
                    ENTITY_PATH_KEY: stop_time.path,
                    "tripId": trip_id,
                    "stopId": stop_id,
                    "assignedStopId": assigned,
                },
            )
        )
    return found
