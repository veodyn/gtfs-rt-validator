"""S005: `departure_occupancy_status` alone, on an update that is not NO_DATA.

`:232`. The clause is a recipe rather than a prohibition: it tells a producer
how to say "I have an occupancy prediction and no time prediction", and the
answer is the stop_time_update's own NO_DATA, whose comment at `:250` says
"Neither arrival nor departure should be supplied". So the three conditions in
the predicate are one shape, and the severity is WARNING because the sentence
says `should`.

Two things the sentence names precisely and this rule does not widen. The
relationship is the **stop_time_update's**, not the trip's. And the test on
arrival and departure is presence: an empty `StopTimeEvent` counts as supplied
here, and an empty one carrying no delay and no time is E044's business.

`departure_occupancy_status` is post-2015, so nothing in the 56 reaches it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import NO_DATA, relationships
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S005"

CLAUSE = (
    "In order to provide departure_occupancy_status without either arrival or departure "
    "StopTimeEvents, ScheduleRelationship should be set to NO_DATA."
)

ALONE = (
    "trip_id {trip_id} stop_time_update[{index}] has only departure_occupancy_status "
    "but is {relationship}"
)

FIELD = "departure_occupancy_status"


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per update that took the shape the clause has a remedy for."""
    return [
        found
        for record in relationships(message, ctx)
        if record.payload == "trip_update"
        for found in _of_trip(record)
    ]


def _of_trip(record: TripRelationship) -> list[Occurrence]:
    trip_id = record.trip.get("trip_id")
    return [
        Occurrence(
            RULE_ID,
            ALONE.format(
                trip_id=trip_id, index=stop_time.index, relationship=stop_time.relationship
            ),
            {
                ENTITY_PATH_KEY: stop_time.path,
                "tripId": trip_id,
                "scheduleRelationship": stop_time.relationship,
            },
        )
        for stop_time in record.stop_time_updates
        if stop_time.update.has(FIELD)
        and not stop_time.update.has("arrival")
        and not stop_time.update.has("departure")
        and stop_time.relationship != NO_DATA
    ]
