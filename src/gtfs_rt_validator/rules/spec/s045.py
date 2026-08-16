"""S045: a selected trip a REPLACEMENT `TripUpdate` has already claimed.

Cites `1198#1`, the second sentence of the `SelectedTrips.trip_ids` comment:

> A `TripUpdate` with `schedule_relationship=REPLACEMENT` must not already exist
> for the trip.

`must not` is where the ERROR comes from. The `TripModifications` is itself what
replaces the trip, so a `TripUpdate` already declaring REPLACEMENT for the same
`trip_id` is two producers describing one replacement, and a consumer has no way
to choose between them.

**Only REPLACEMENT counts.** A trip carrying an ordinary `TripUpdate` is the
normal case for a detour, which changes the stops of a trip that is otherwise
running and predicted as usual. Firing on that would report almost every correct
feed that publishes both messages, which is the over-firing failure mode a tier
with no oracle ships.

**Scope is the cycle, not the message.** "Already exist" is a claim about the
feed at an instant, and the sentence names no file; this project's feed at an
instant is one message per role, which `runner/context.py` calls a cycle. An
agency publishing its `TripModifications` in one role file and the REPLACEMENT
`TripUpdate` in another has written exactly the feed the clause forbids, and a
rule reading only the message it was handed would see neither half of it.

So this reads `ctx.combined`, the fourth rule to do so after E047, W003 and
S020, and it obeys the same contract: the combined view reaches exactly one
message per cycle, its host, so the rule fires once per cycle rather than once
per role and returns early on every other message. Each role's index is asked
for separately, and an occurrence carries the file of the role its
`TripModifications` is in rather than the host's, because a reader sent to the
wrong file cannot act on the finding.

The first cut of this rule was message-scoped, on the ground that the combined
view and a per-role index were a mechanism no rule used yet. S020 landed that
mechanism in the same tier while this was being written, so the reason expired;
"in the same cycle" is what this rule was specified as throughout, and
`tests/test_rule_s045.py` pins it.

`TripModifications` postdates the jar, so nothing in the differential can confirm
this rule or refute the claim that no upstream rule borders it: `OVERLAP` in
`tests/test_tier_overlap.py` names no neighbour for S045.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.manifest import Severity
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, SOURCE_FILE_KEY, Occurrence
from gtfs_rt_validator.rules._shared.feed_index import index
from gtfs_rt_validator.rules._shared.walk_trip_modifications import trip_modifications
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import CombinedFeed, RuleContext, RuleResult

RULE_ID = "S045"

CLAUSE = (
    "spec: A `TripUpdate` with `schedule_relationship=REPLACEMENT` must not already exist "
    "for the trip."
)

TAKEN = "trip_id {trip_id} already has a TripUpdate with schedule_relationship REPLACEMENT"


@rule(RULE_ID, source=CLAUSE, severity=Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """Every `trip_id` of every `SelectedTrips` in the cycle, against its index."""
    combined = ctx.combined
    if combined is None:
        return None
    replaced = _replaced_in(message, ctx, combined)
    if not replaced:
        return None
    return list(_conflicts(ctx, combined, replaced))


def _replaced_in(message: Msg, ctx: RuleContext, combined: CombinedFeed) -> frozenset[str]:
    """Every `trip_id` the cycle already declares REPLACEMENT, across every role.

    The host's own message is indexed with no scope, which is the entry every
    other rule on this message shares; each further role gets its own. Same shape
    as S020's `_created_in`, and for the same reason.
    """
    replaced: set[str] = set()
    for role in combined.roles():
        other = combined.message(role)
        scope = "" if other is message else role
        replaced |= set(index(other, ctx, scope=scope).replacement_trip_updates)
    return frozenset(replaced)


def _conflicts(
    ctx: RuleContext, combined: CombinedFeed, replaced: frozenset[str]
) -> Iterator[Occurrence]:
    """Roles in `ROLE_ORDER`, then entity order, so one cycle reports one way."""
    for role in combined.roles():
        for record in trip_modifications(combined.message(role), ctx):
            for position, selected in enumerate(record.owner.get("selected_trips")):
                for offset, trip_id in enumerate(selected.get("trip_ids")):
                    if trip_id in replaced:
                        yield Occurrence(
                            RULE_ID,
                            TAKEN.format(trip_id=trip_id),
                            {
                                SOURCE_FILE_KEY: combined.source(role),
                                ENTITY_PATH_KEY: (
                                    f"{record.path}.selected_trips[{position}].trip_ids[{offset}]"
                                ),
                            },
                        )
