"""S014: a `TripProperties` field populated on a trip that is not DUPLICATED.

The second half of the sentence S013 takes the first half of, written three
times over `TripProperties.trip_id` (`:392`), `start_date` (`:395`) and
`start_time` (`:409`): "otherwise this field must not be populated and will be
ignored by consumers." The consequence is in the clause, which is what makes it
worth reporting: the value is not merely unnecessary, it is discarded, so a
producer that meant something by it has lost it silently.

**Only those three fields.** `TripProperties` also declares `shape_id` and
`trip_headsign`, and neither carries this sentence; `shape_id`'s own comment
describes a detour on an ordinary scheduled trip, which is the opposite of
forbidden. `_shared/trip_properties.py` holds the three names so this rule and
S013 cannot drift apart on them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import DUPLICATED, relationships
from gtfs_rt_validator.rules._shared.trip_properties import MESSAGE, path, populated
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S014"

CLAUSE = (
    "Required if schedule_relationship=DUPLICATED, otherwise this field must not be populated "
    "and will be ignored by consumers."
)

FORBIDDEN = "trip_id {trip_id} is {relationship} and {message}.{field} must not be populated"


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per field a trip that is not DUPLICATED filled in."""
    return [
        found
        for record in relationships(message, ctx)
        if record.payload == "trip_update" and record.relationship != DUPLICATED
        for found in _of_trip(record)
    ]


def _of_trip(record: TripRelationship) -> list[Occurrence]:
    trip_id = record.trip.get("trip_id")
    return [
        Occurrence(
            RULE_ID,
            FORBIDDEN.format(
                trip_id=trip_id,
                relationship=record.relationship,
                message=MESSAGE,
                field=field,
            ),
            {
                ENTITY_PATH_KEY: path(record),
                "tripId": trip_id,
                "field": field,
                "scheduleRelationship": record.relationship,
            },
        )
        for field in populated(record)
    ]
