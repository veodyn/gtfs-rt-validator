"""S020: a DUPLICATED VehiclePosition whose trip_id no TripUpdate created.

`:806`. The two messages of a duplicate say different things with the same
field: on a TripUpdate the descriptor's `trip_id` names the GTFS trip being
copied (`:873`), and on a VehiclePosition it names the copy, which exists only
because some `TripUpdate.TripProperties.trip_id` declared it. `880#1` states the
same pairing from the enum's side and the verdict file folds it into this rule.

**It reads the cycle, not the message.** An agency that publishes `-tu` and
`-vp` separately still has to satisfy the clause, so this is the third rule in
the project to read `ctx.combined`, after E047 and W003, and it obeys the same
contract: the combined view reaches exactly one message per cycle, its host, so
the rule fires once per cycle rather than once per role and returns early on
every other message. Under `--compat` that mechanism exists too, with one
unnamed role, which is why this rule's isolation from compat is the registry's
job and not the descriptor's.

`feed_index.index` is asked once per role, with the role as its `scope` for
every message that is not the one this rule was called with. `memo.py` says why
the scope is needed: without it the second role's question would be answered
with the first role's index.

**Not E047**, which pairs `TripDescriptor.trip_id` against `VehicleDescriptor.id`
across the two feeds. This pairs a `trip_id` against a different field on the
other side, one E047 never reads.

A DUPLICATED VehiclePosition with no `trip_id` at all is reported: the sentence
says the field "must contain the value", and it contains nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, SOURCE_FILE_KEY, Occurrence
from gtfs_rt_validator.rules._shared.feed_index import index
from gtfs_rt_validator.rules._shared.schedule_relationship import DUPLICATED, trip_relationship
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import CombinedFeed, RuleContext, RuleResult

RULE_ID = "S020"

CLAUSE = (
    "When schedule_relationship is DUPLICATED within a VehiclePosition, the trip_id identifies "
    "the new duplicate trip and must contain the value for the corresponding "
    "TripUpdate.TripProperties.trip_id."
)

UNMATCHED = (
    "vehicle trip_id {trip_id} is DUPLICATED but no TripUpdate.TripProperties.trip_id matches"
)


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per DUPLICATED vehicle the cycle's TripUpdates never made."""
    combined = ctx.combined
    if combined is None:
        return None
    created = _created_in(message, ctx, combined)
    return [
        _found(combined, role, entity_index, entity.get("vehicle"))
        for role, entity_index, entity in combined.entities()
        if entity.has("vehicle")
        and trip_relationship(entity.get("vehicle").get("trip")) == DUPLICATED
        and entity.get("vehicle").get("trip").get("trip_id") not in created
    ]


def _created_in(message: Msg, ctx: RuleContext, combined: CombinedFeed) -> frozenset[str]:
    """Every `TripProperties.trip_id` the cycle declares, across every role.

    The host's own message is indexed with no scope, which is the entry every
    other rule on this message shares; each further role gets its own.
    """
    created: set[str] = set()
    for role in combined.roles():
        other = combined.message(role)
        scope = "" if other is message else role
        created |= set(index(other, ctx, scope=scope).trip_property_trip_ids)
    return frozenset(created)


def _found(combined: CombinedFeed, role: str, entity_index: int, position: Msg) -> Occurrence:
    trip_id = position.get("trip").get("trip_id")
    return Occurrence(
        RULE_ID,
        UNMATCHED.format(trip_id=trip_id),
        {
            SOURCE_FILE_KEY: combined.source(role),
            ENTITY_PATH_KEY: f"entity[{entity_index}].vehicle",
            "tripId": trip_id,
        },
    )
