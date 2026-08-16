"""One pass over the message's `TripModifications`, read by eight spec-tier rules.

S041 checks that a `Modification` declares a `start_stop_selector`, S042 reads
its two `StopSelector` fields, S046 and S047 resolve a `ReplacementStop.stop_id`,
and S048 checks that `travel_time_to_stop` increases across a modification's
replacement stops. S044, S045, S049 and S050 read `selected_trips` and
`service_dates`, which sit on the `TripModifications` itself. One walk serves all
eight; `memo.py` says why it happens once.

**Three views, because the eight rules do not ask one question.** The obvious
shape for this walk is a flat
`(modification_index, modification, replacement_stop_index, replacement_stop)`,
and flat alone cannot serve most of its readers. A modification carrying no
replacement stop contributes no row to a flat stream, so S041 could never see
the modification it is about; S048's monotonicity is *within* a modification, so
a stream that lost the grouping would let it compare the last stop of one
modification against the first of the next and report a decrease the clause says
nothing about; and a `TripModifications` carrying no `Modification` at all is
still a `TripModifications` whose `selected_trips` and `service_dates` four rules
have to read. So `trip_modifications` yields the owners, `modifications` yields
the grouped records inside them, and `replacement_stops` flattens those, which is
the flat stream with both groupings still reachable.

**The owner view is not an optimisation.** `selected_trips` and `service_dates`
are fields of `TripModifications`, and nothing in the proto requires a
`TripModifications` to carry a `Modification`: a producer announcing the dates
and the trips of a detour before its stop-level shape is settled writes exactly
that message. Deriving the owners from the modifications would make S044, S045,
S049 and S050 silent on it, which is the failure mode with no oracle to catch it.

**Presence is tested before the payload is read.** `getTripModifications()` on
an entity that names none answers a default instance whose `modifications` list
is empty, so a walk that skipped the test would still come out with the right
count today and would be wrong the moment anything here read a default.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.rules._shared.memo import memoised

if TYPE_CHECKING:  # Type-only: nothing under `rules/` may import the runner at
    # run time, because it reaches the static layer and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = [
    "SELECTOR_FIELDS",
    "ModificationRecord",
    "ReplacementStopRecord",
    "TripModificationsRecord",
    "modifications",
    "replacement_stops",
    "trip_modifications",
]


#: The fields of `Modification` that carry a `StopSelector`, in declaration
#: order. S042 reads both for emptiness and S043 reads both for a `stop_id`, and
#: two rules spelling the pair separately is how they come to disagree about
#: where a selector lives. `tests/test_rule_s042.py` asserts this is the whole
#: surface `schema_current` declares, so a third site at a later pin is red.
SELECTOR_FIELDS = ("start_stop_selector", "end_stop_selector")


@dataclass(frozen=True, slots=True)
class ReplacementStopRecord:
    """One `ReplacementStop`, and where in the message it was found."""

    index: int
    stop: Msg
    path: str


@dataclass(frozen=True, slots=True)
class ModificationRecord:
    """One `Modification`, with the replacement stops that belong to it.

    `owner` is the `TripModifications` it came from, which carries the
    `selected_trips` and `service_dates` a rule reporting against this
    modification may want to name.
    """

    entity_index: int
    index: int
    modification: Msg
    owner: Msg
    path: str
    replacement_stops: tuple[ReplacementStopRecord, ...]


@dataclass(frozen=True, slots=True)
class TripModificationsRecord:
    """One `TripModifications` entity, with the modifications it declares.

    `owner` is the message itself, which is where `selected_trips`,
    `start_times` and `service_dates` live. `entity_id` is the `FeedEntity.id`
    that carried it, kept because a report naming only an index makes a reader
    count entities to find the one it means.
    """

    entity_index: int
    entity_id: str
    owner: Msg
    path: str
    modifications: tuple[ModificationRecord, ...]


def trip_modifications(message: Any, ctx: RuleContext) -> tuple[TripModificationsRecord, ...]:
    """Every `TripModifications` of `message`, walked at most once per context."""
    return memoised(_build, message, ctx)


def modifications(message: Any, ctx: RuleContext) -> tuple[ModificationRecord, ...]:
    """Every `Modification` of `message`, off the same walk.

    Reads the memoised owners rather than walking again, so a rule reaching for
    this view costs nothing over a rule reaching for the owners.
    """
    return tuple(
        record for owner in trip_modifications(message, ctx) for record in owner.modifications
    )


def replacement_stops(
    message: Any, ctx: RuleContext
) -> Iterator[tuple[ModificationRecord, ReplacementStopRecord]]:
    """The same walk flattened: every replacement stop, with its modification.

    Reads the memoised records rather than walking again, so a rule reaching for
    the flat view costs nothing over a rule reaching for the grouped one.
    """
    for record in modifications(message, ctx):
        for stop in record.replacement_stops:
            yield record, stop


def _build(message: Any, ctx: RuleContext) -> tuple[TripModificationsRecord, ...]:
    found: list[TripModificationsRecord] = []
    for entity_index, entity in enumerate(message.get("entity")):
        if not entity.has("trip_modifications"):
            continue
        owner = entity.get("trip_modifications")
        path = f"entity[{entity_index}].trip_modifications"
        found.append(
            TripModificationsRecord(
                entity_index=entity_index,
                entity_id=entity.get("id"),
                owner=owner,
                path=path,
                modifications=tuple(_of_owner(entity_index, owner, path)),
            )
        )
    return tuple(found)


def _of_owner(entity_index: int, owner: Msg, path: str) -> Iterator[ModificationRecord]:
    for index, modification in enumerate(owner.get("modifications")):
        here = f"{path}.modifications[{index}]"
        yield ModificationRecord(
            entity_index=entity_index,
            index=index,
            modification=modification,
            owner=owner,
            path=here,
            replacement_stops=tuple(_stops(modification, here)),
        )


def _stops(modification: Msg, path: str) -> Iterator[ReplacementStopRecord]:
    for index, stop in enumerate(modification.get("replacement_stops")):
        yield ReplacementStopRecord(
            index=index, stop=stop, path=f"{path}.replacement_stops[{index}]"
        )
