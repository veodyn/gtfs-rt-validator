"""An id the pinned proto lets resolve two ways, and the one way it is reported.

`TripModifications` introduced references that may point either into the static
feed or into the realtime feed carrying them. `ReplacementStop.stop_id` resolves
against `stops.txt` **or** a `Stop` entity of the same message;
`SelectedTrips.shape_id` resolves against `shapes.txt` **or** a `Shape` entity.
That widened resolution set is the whole reason S046 is not E011: E011's world
has no realtime-defined stops in it, so pointing it at that field would report a
correct feed as broken.

**Which caller gets which entry point, because the two fields are not the same
field.** `stop_resolves` and `Reference.unresolved` serve S046 and S044, whose
clauses say outright that the value "may refer to a new stop added using a
GTFS-RT `Stop` message in the same GTFS-RT feed" (`:1259`) or a `Shape` entity
(`:1202`). `selected_stop_resolves` and `selected_stop_unresolved` serve S043
alone, whose clause is the one sentence "Must be the same as in stops.txt in the
corresponding GTFS feed" (`:1242`) and names no second place. Reading a
`StopSelector` through the widened pair was this module's first shape and it was
wrong: `:1163` says a `start_stop_selector` names "the first stop_time of the
**original** trip", and a stop the realtime feed invents is not on the original
trip. It is a `ReplacementStop`, which is the other half of the same
`Modification`.

**The occurrence text is here because the clause is the same sentence three
times.** `1202#1` and `1261#1` are the same sentence about two different fields,
and both exist to warn against one substitution: writing the `FeedEntity.id`
where the id *inside* the entity was meant. A rule that reported only
"unresolvable" would throw away the finding its own citation was written for, so
`unresolved` says which two places were searched and, when the value is a
`FeedEntity.id` of this message, says that too.

Stdlib plus this project's own decoded messages. Nothing here reads the runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from gtfs_rt_validator.rules._shared.feed_index import FeedIndex

if TYPE_CHECKING:  # Type-only: nothing under `rules/` may import the runner at
    # run time, because it reaches the static layer and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = [
    "SELECTED_STOP_IS_NEW",
    "SELECTED_STOP_MISSING",
    "SHAPE",
    "STOP",
    "Reference",
    "selected_stop_resolves",
    "selected_stop_unresolved",
    "stop_resolves",
]


@dataclass(frozen=True, slots=True)
class Reference:
    """One field that names something defined in either feed, and how to say so.

    `field` is the proto field name, `table` the static file it may name, and
    `entity` the realtime message that may define it instead. Three values
    rather than a formatted string, because the two instances below differ in
    all three and a reader of a report should not have to know which rule wrote
    which sentence.
    """

    field: str
    table: str
    entity: str

    def unresolved(self, value: str, feed: FeedIndex) -> str:
        """The occurrence prefix for a value that resolved in neither place."""
        confused = (
            f", and is the id of a FeedEntity rather than the {self.field} inside one"
            if value in feed.entity_ids
            else ""
        )
        return (
            f"{self.field} {value} is in neither {self.table} nor a "
            f"{self.entity} entity of this feed{confused}"
        )


#: `ReplacementStop.stop_id`, for S046. **Not `StopSelector.stop_id`**, which
#: resolves one way only and has its own entry point below.
STOP = Reference(field="stop_id", table="stops.txt", entity="Stop")

#: `SelectedTrips.shape_id`, for S044.
SHAPE = Reference(field="shape_id", table="shapes.txt", entity="Shape")


#: `StopSelector.stop_id`, for S043, and deliberately not a `Reference`: `:1242`
#: pins the field to one table, so there is no second place to name.
SELECTED_STOP_MISSING = "stop_id {stop_id} is not in stops.txt"

#: The tail that names the mistake worth naming, when the value is a stop this
#: feed defines. `ReplacementStop.stop_id` is where a new stop belongs; a
#: `StopSelector` selects one of the original trip's own stop_times.
SELECTED_STOP_IS_NEW = ", and the Stop entity of this feed that defines it is a new stop"


def selected_stop_resolves(stop_id: str, ctx: RuleContext) -> bool:
    """Whether `stop_id` is in `stops.txt`, the only place `:1242` permits.

    No `FeedIndex` argument, and that absence is the contract: a `Stop` entity
    of the same feed cannot answer this question, so a caller cannot pass one in
    by mistake. `stop_resolves` below is the widened form, for the two fields
    whose own comments permit it.
    """
    return stop_id in ctx.static.stop_ids


def selected_stop_unresolved(stop_id: str, feed: FeedIndex) -> str:
    """How S043 says `stops.txt` does not have this stop.

    `feed` is read only to tell a producer who invented the stop from one who
    mistyped it. It must be the index over the **whole** message, for the
    ordering reason `feed_index.py` carries.
    """
    tail = SELECTED_STOP_IS_NEW if feed.defines_stop(stop_id) else ""
    return f"{SELECTED_STOP_MISSING.format(stop_id=stop_id)}{tail}"


def stop_resolves(stop_id: str, ctx: RuleContext, feed: FeedIndex) -> bool:
    """Whether `stop_id` names a stop either feed defines.

    `feed` is the index over the message the reference was found in, and it
    must be over the **whole** message: `FeedEntity` ordering is not specified,
    so a `TripModifications` may precede the `Stop` entity it names.
    `feed_index.py` carries that argument in full.
    """
    return stop_id in ctx.static.stop_ids or feed.defines_stop(stop_id)
