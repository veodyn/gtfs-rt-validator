"""S015: a `TripProperties.trip_id` that the (CSV) GTFS already uses.

`:388`. The field names the *new* trip a DUPLICATED TripUpdate creates, so the
whole point of it is that the id is new: `:386` says it "Defines the identifier
of a new trip that is a duplicate of an existing trip defined in (CSV) GTFS
trips.txt but will start at a different service date and/or time". An id taken
from `trips.txt` makes the duplicate indistinguishable from the trip it
duplicates, and every downstream reference ambiguous.

**Read off the field, not off the relationship.** The sentence sits on
`TripProperties.trip_id` and says nothing about `schedule_relationship`, so a
producer that populated the field under some other relationship has still
collided with GTFS. That the field should not be populated there at all is
S014's separate finding on its own separate clause.

Not E016, which fires on a `TripDescriptor.trip_id` that GTFS knows under an
ADDED relationship. Different message, different field, and the jar is asked
about the difference rather than trusted on it in
`tests/test_spec_tier_does_not_shadow_the_jar.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import relationships
from gtfs_rt_validator.rules._shared.trip_properties import MESSAGE, path, properties
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S015"

CLAUSE = "Its value must be different than the ones used in the (CSV) GTFS."

COLLIDES = "{message}.trip_id {trip_id} is already a trip_id in the (CSV) GTFS"

FIELD = "trip_id"


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per new trip id `trips.txt` already carries."""
    return [
        _found(record)
        for record in relationships(message, ctx)
        if record.payload == "trip_update"
        and properties(record).has(FIELD)
        and properties(record).get(FIELD) in ctx.static.trips
    ]


def _found(record: TripRelationship) -> Occurrence:
    new_trip_id = properties(record).get(FIELD)
    return Occurrence(
        RULE_ID,
        COLLIDES.format(message=MESSAGE, trip_id=new_trip_id),
        {ENTITY_PATH_KEY: path(record), "tripId": new_trip_id},
    )
