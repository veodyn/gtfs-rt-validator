"""S019: a route-scoped TripUpdate predicting a delay instead of a time.

The sentence after S018's, in the same `TripDescriptor` message comment:

    In addition, absolute arrival/departure times must be provided.

"In addition" is to the previous sentence's antecedent, so this rule shares
S018's: a descriptor naming a route and no trip. A `delay` is relative to a
scheduled time, and a route-scoped prediction names no trip whose schedule could
supply one, so a delay there resolves to nothing.

**Not E044, and the band is disjoint.** E044 fires for a StopTimeEvent carrying
neither `delay` nor `time`, accepting either. This rule accepts only `time`, so
the fixture that separates them is a `delay` with no `time`, which E044 is
content with. A StopTimeEvent carrying neither violates both clauses and is
reported by both; that overlap is the one this rule declares, recorded as E044
in `OVERLAP` in `tests/test_tier_overlap.py`, and it is not a duplicate, because
neither rule's set of findings contains the other's.

An *absent* arrival or departure is not this rule's finding. The clause is about
the times a producer provides, and whether one has to be provided at all is
E043's question on a different antecedent.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import (
    StopTimeRelationship,
    relationships,
)
from gtfs_rt_validator.rules._shared.trip_descriptor_spec import route_scoped, route_text
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S019"

CLAUSE = "spec: In addition, absolute arrival/departure times must be provided."

#: The two `StopTimeEvent` fields the sentence names, in declaration order, so
#: an update carrying both reports arrival before departure.
EVENTS = ("arrival", "departure")


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        occurrence
        for found in relationships(message, ctx)
        if found.payload == "trip_update" and route_scoped(found.trip)
        for stop in found.stop_time_updates
        for occurrence in _timeless(stop, route_text(found.trip))
    ]


def _timeless(stop: StopTimeRelationship, route: str) -> Iterator[Occurrence]:
    """Each `StopTimeEvent` this update wrote that carries no absolute time."""
    for name in EVENTS:
        if stop.update.has(name) and not stop.update.get(name).has("time"):
            yield Occurrence(
                RULE_ID,
                f"{route} stop_time_update[{stop.index}].{name} has no time",
                {ENTITY_PATH_KEY: f"{stop.path}.{name}"},
            )
