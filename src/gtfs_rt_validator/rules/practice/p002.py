"""P002: the `FeedEntity.id` carrying a trip changed between two messages.

`:44`, the `FeedEntity.id` row of the entity table. A consumer keys its own
state on the entity id, so a producer that renumbers entities every iteration
makes every trip look new: the consumer cannot tell an updated trip from a
replacement, and any state it kept about the trip is orphaned each time. The
document's `:18` imperative says the same thing in the general form ("Maintain
persistent identifiers (id fields) within a GTFS Realtime feed ... across feed
iterations"), and the verdict file folds it into this rule and P003.

**The comparison is against the previous message of the same role**, and this
rule does not decide that: `_shared/walk_sequence_ids.py` reads `ctx.previous`
and nothing else, and `runner/context.py` settles what `previous` means. It
matters here more than anywhere: a rule that compared a VehiclePositions message
against the TripUpdates message beside it in the same cycle would report every
trip in a two-feed run, every cycle.

**A trip only one of the two messages carries is not a change.** The walk yields
a record only when both messages carry the trip, so a first sighting is silent
and so is a trip that has just ended. Absence is not instability: `:44` is about
an id that moved, and a trip that has no earlier id has nothing to have moved
from.

**One answer per payload per trip.** A combined feed carries a TripUpdate and a
VehiclePosition for one trip under two different entity ids, and their order in
the entity list is specified nowhere, so the walk keys on the payload and the
trip together. Its docstring has the argument; the consequence here is that such
a feed reports at most one occurrence per payload rather than one bogus one for
whichever entity happened to sort first.

**No overlap with the 56, and the reason is structural rather than measured.**
Every upstream rule sees one message: `BatchProcessor` carries the previous
message only to compare header timestamps (W007) and to abort on an identical
one, and no validator is handed both messages' entity lists.
`tests/test_practice_tier_does_not_shadow_the_jar.py` records what the jar
actually said over this rule's fixture, which is nothing.

`FeedEntity.id` is `required` in both schemas and `proto/decode.py` refuses an
entity without it, so there is no absent-id branch here and none is possible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_sequence_ids import sequence_ids
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.walk_sequence_ids import SequencedTrip
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P002"

CLAUSE = "Should be kept stable over the entire trip duration"

MOVED = (
    "the {payload} carrying trip_id {trip_id} has entity id {current} in this message "
    "and had {previous} in the previous message of this feed"
)


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per trip whose entity id moved, in this message's order."""
    return [
        _found(record)
        for record in sequence_ids(message, ctx)
        if record.current.entity_id != record.previous.entity_id
    ]


def _found(record: SequencedTrip) -> Occurrence:
    return Occurrence(
        RULE_ID,
        MOVED.format(
            payload=record.payload,
            trip_id=record.trip_id,
            current=record.current.entity_id,
            previous=record.previous.entity_id,
        ),
        {
            ENTITY_PATH_KEY: record.current.path,
            "tripId": record.trip_id,
            "entityId": record.current.entity_id,
            "previousEntityId": record.previous.entity_id,
        },
    )
