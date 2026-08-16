"""S017: `TripUpdate.delay` on a NEW trip.

`:362`, and a WARNING because the sentence says `should`. `169#1` is the
message-level statement of the same thing, "- delay should be used when the
prediction is given relative to some existing schedule in GTFS", and the verdict
file records it as `folded` into this rule rather than as a second one.

**Why NEW is the whole scope**, read off the enum rather than assumed. `:900`
defines NEW as "An extra trip unrelated to any existing trips", which is exactly
"no existing schedule in GTFS". Every other member relates to one: SCHEDULED,
CANCELED, DELETED and UNSCHEDULED are the GTFS trip; DUPLICATED copies one and
`:873` says the original is named by `TripUpdate.TripDescriptor.trip_id`;
REPLACEMENT replaces one. So a delay is meaningful for all of them and
meaningless for NEW alone.

Presence, not truth: `delay = 0` means "exactly on time" (`:366`) relative to a
schedule a NEW trip does not have, so it is reported like any other value.

Not E046, which compares a stop_time_update's delay against `stop_times.txt`.
Different field, different message, and this rule opens no static feed at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import NEW, relationships
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S017"

CLAUSE = (
    "Delay should only be specified when the prediction is given relative to some existing "
    "schedule in GTFS."
)

UNRELATED = "trip_id {trip_id} has delay {delay} on a NEW trip"

FIELD = "delay"


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per NEW TripUpdate carrying a trip-level delay."""
    return [
        _found(record)
        for record in relationships(message, ctx)
        if record.payload == "trip_update"
        and record.relationship == NEW
        and record.owner.has(FIELD)
    ]


def _found(record: TripRelationship) -> Occurrence:
    trip_id = record.trip.get("trip_id")
    delay = record.owner.get(FIELD)
    return Occurrence(
        RULE_ID,
        UNRELATED.format(trip_id=trip_id, delay=delay),
        {ENTITY_PATH_KEY: record.path, "tripId": trip_id, FIELD: delay},
    )
