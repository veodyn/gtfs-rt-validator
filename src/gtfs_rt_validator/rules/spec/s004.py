"""S004: `StopTimeEvent.scheduled_time` where the clause forbids it.

`:201`, one sentence carrying both halves: optional for NEW, REPLACEMENT and
DUPLICATED, "forbidden otherwise". The exempt set is not arbitrary. Those three
are exactly the relationships that produce a trip GTFS carries no schedule for,
which is what the field is for: `:198` calls it "Scheduled time for a NEW,
REPLACEMENT, or DUPLICATED trip".

The relationship read is the **trip's**, as the sentence says
(`TripUpdate.schedule_relationship`), not the stop_time_update's, and it is the
resolved value rather than the declared one: an absent field is SCHEDULED to
every consumer, so a producer that omits it has not thereby earned the
exemption.

`scheduled_time` and `NEW` are both post-2015, so the 2015 descriptor decodes
neither and no upstream rule can express this.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import (
    DUPLICATED,
    NEW,
    REPLACEMENT,
    relationships,
)
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S004"

CLAUSE = (
    "Optional if TripUpdate.schedule_relationship is NEW, REPLACEMENT or DUPLICATED, "
    "forbidden otherwise."
)

FORBIDDEN = (
    "trip_id {trip_id} stop_time_update[{index}] {event} has scheduled_time "
    "on a {relationship} trip"
)

#: The three the sentence names. Everything else is "otherwise".
PERMITTED = (NEW, REPLACEMENT, DUPLICATED)

#: `StopTimeUpdate`'s two `StopTimeEvent` fields, in field-number order, which
#: is the order an occurrence pair reads in.
EVENTS = ("arrival", "departure")

FIELD = "scheduled_time"


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per event carrying `scheduled_time` on a forbidden trip."""
    return [
        found
        for record in relationships(message, ctx)
        if record.payload == "trip_update" and record.relationship not in PERMITTED
        for found in _of_trip(record)
    ]


def _of_trip(record: TripRelationship) -> list[Occurrence]:
    trip_id = record.trip.get("trip_id")
    return [
        Occurrence(
            RULE_ID,
            FORBIDDEN.format(
                trip_id=trip_id,
                index=stop_time.index,
                event=event,
                relationship=record.relationship,
            ),
            {
                ENTITY_PATH_KEY: f"{stop_time.path}.{event}",
                "tripId": trip_id,
                "scheduleRelationship": record.relationship,
            },
        )
        for stop_time in record.stop_time_updates
        for event in EVENTS
        if stop_time.update.has(event) and stop_time.update.get(event).has(FIELD)
    ]
