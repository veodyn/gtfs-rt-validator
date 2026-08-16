"""S013: a DUPLICATED trip missing one of the three `TripProperties` fields.

The first half of a sentence the proto writes three times, once on each of
`TripProperties.trip_id` (`:392`), `start_date` (`:395`) and `start_time`
(`:409`): "Required if schedule_relationship=DUPLICATED, otherwise this field
must not be populated and will be ignored by consumers." S014 takes the second
half. The verdict file records both rules against all three clauses as
`rule_in_part`, which is why the two quote the same text and neither claims the
sentence whole.

The three fields are what make a duplicate nameable: `:874` says DUPLICATED
copies "an existing trip from static GTFS but start at a different service date
and/or time", and the copy has no identity without them.

**One occurrence per missing field**, because the sentence is written per field.
A producer told only that the trip_properties are wrong has to guess which.

`TripProperties` hangs off `TripUpdate` and nothing else, so a DUPLICATED
VehiclePosition is out of scope here and is S020's subject instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import DUPLICATED, relationships
from gtfs_rt_validator.rules._shared.trip_properties import MESSAGE, missing, path
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S013"

CLAUSE = (
    "Required if schedule_relationship=DUPLICATED, otherwise this field must not be populated "
    "and will be ignored by consumers."
)

REQUIRED = "trip_id {trip_id} is DUPLICATED and {message}.{field} is required"


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per field a DUPLICATED trip left out."""
    return [
        found
        for record in relationships(message, ctx)
        if record.payload == "trip_update" and record.relationship == DUPLICATED
        for found in _of_trip(record)
    ]


def _of_trip(record: TripRelationship) -> list[Occurrence]:
    trip_id = record.trip.get("trip_id")
    return [
        Occurrence(
            RULE_ID,
            REQUIRED.format(trip_id=trip_id, message=MESSAGE, field=field),
            {
                ENTITY_PATH_KEY: path(record),
                "tripId": trip_id,
                "field": field,
            },
        )
        for field in missing(record)
    ]
