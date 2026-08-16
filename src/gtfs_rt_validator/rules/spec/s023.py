"""S023: a TripDescriptor written both as a modified trip and as a plain one.

`TripDescriptor.modified_trip`'s comment, at `:929`:

    If this field is provided, the `trip_id`, `route_id`, `direction_id`,
    `start_time`, `start_date` fields of the `TripDescriptor` MUST be left
    empty, to avoid confusion by consumers that aren't looking for the
    `ModifiedTripSelector` value.

The selector names the trip indirectly, through the `TripModifications` entity
that modifies it, and the five fields name it directly. A descriptor carrying
both states the trip twice and a consumer reading only one of the two forms gets
whichever the producer happened to make right.

The five are spelled out here because the clause spells them out. A sixth field
arriving at a later pin changes the sentence, which fails the citation gate,
which is the signal to change this tuple in the same commit.

One occurrence per descriptor rather than one per field: the defect is the
descriptor being written two ways at once, and reporting a five-field descriptor
five times would say the same thing five times.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import relationships
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S023"

CLAUSE = (
    "spec: If this field is provided, the `trip_id`, `route_id`, `direction_id`, "
    "`start_time`, `start_date` fields of the `TripDescriptor` MUST be left empty, to "
    "avoid confusion by consumers that aren't looking for the `ModifiedTripSelector` value."
)

#: The five the clause names, in the order it names them, so an occurrence
#: listing several reads in the sentence's own order.
EMPTIED = ("trip_id", "route_id", "direction_id", "start_time", "start_date")


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"{_selector_text(found.trip)} is set together with {', '.join(populated)}",
            {ENTITY_PATH_KEY: found.path},
        )
        for found in relationships(message, ctx)
        if found.trip.has("modified_trip")
        for populated in [tuple(name for name in EMPTIED if found.trip.has(name))]
        if populated
    ]


def _selector_text(trip: Msg) -> str:
    """`modified_trip M1`, or the bare field name when it declares no id.

    `modifications_id` is optional, so the alternative is a sentence with an
    empty string interpolated into the middle of it.
    """
    selector = trip.get("modified_trip")
    if selector.has("modifications_id"):
        return "modified_trip " + selector.get("modifications_id")
    return "modified_trip"
