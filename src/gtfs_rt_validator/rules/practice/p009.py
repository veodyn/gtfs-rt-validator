"""P009: a NEW trip that states no `TripProperties.trip_headsign`.

`:78`, the recommendation row for `TripProperties.trip_headsign` in the pinned
Best Practices. A NEW trip is one GTFS carries nothing at all for, so the
headsign is the only thing that tells a rider where the vehicle is going;
without it a consumer has an arrival prediction for a trip it cannot name.

**This rule enforces the first half of its clause, deliberately.** The sentence
is "Should always be provided for a trip with `TripDescriptor.schedule_relationship`
= `NEW`, and provided for a trip with `TripDescriptor.schedule_relationship` =
`REPLACEMENT` if the trip is diverted." The NEW half is unconditional and
therefore checkable. The REPLACEMENT half is conditioned on "if the trip is
diverted", and **no field of a GTFS-Realtime feed states that a trip is
diverted**: `TripDescriptor` carries no such flag, and inferring one from an
`Alert` with `effect = DETOUR` would be this project deciding what the
document's antecedent means. So a REPLACEMENT trip with no headsign is silent
here, and `upstream/practice-clause-verdicts.json` records the clause as
`rule_in_part` with that narrowing written down. The citation quotes the whole
sentence because the citation gate is verbatim; the verdict file is where the
part being enforced is stated.

`trip_properties` hangs off `TripUpdate` and nothing else, so a NEW
VehiclePosition and a NEW `Alert.informed_entity` selector carry no field this
rule could be about, and neither is in scope.

**Under a 2015 decode there is nothing here at all.** `NEW = 8` is not a member
of the 2015 `TripDescriptor.ScheduleRelationship`, so the decoder drops the
field and the trip resolves to SCHEDULED; `TripProperties` is post-2015 as
well. A fixture for this rule looks to the jar like a SCHEDULED trip with an
unknown field, which is why nothing in the 56 can express it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import NEW, relationships
from gtfs_rt_validator.rules._shared.trip_properties import MESSAGE, path, properties
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P009"

CLAUSE = (
    "Should always be provided for a trip with `TripDescriptor.schedule_relationship` = `NEW`, "
    "and provided for a trip with `TripDescriptor.schedule_relationship` = `REPLACEMENT` if the "
    "trip is diverted."
)

#: The field the row is written on. Not in `_shared/trip_properties.FIELDS`,
#: which is S013's and S014's three DUPLICATED fields and a different sentence.
HEADSIGN = "trip_headsign"

MISSING = "trip_id {trip_id} is NEW and {message}.{field} is not provided"


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per NEW TripUpdate whose trip_properties state no headsign.

    Presence, not truthiness: a producer that states the headsign as the empty
    string has stated it. An absent `trip_properties` submessage answers a
    default instance, so "no submessage" and "a submessage with no headsign in
    it" are the same finding, which is the one a reader can act on.
    """
    return [
        _found(record)
        for record in relationships(message, ctx)
        if record.payload == "trip_update"
        and record.relationship == NEW
        and not properties(record).has(HEADSIGN)
    ]


def _found(record: TripRelationship) -> Occurrence:
    trip_id = record.trip.get("trip_id")
    return Occurrence(
        RULE_ID,
        MISSING.format(trip_id=trip_id, message=MESSAGE, field=HEADSIGN),
        {ENTITY_PATH_KEY: path(record), "tripId": trip_id, "field": HEADSIGN},
    )
