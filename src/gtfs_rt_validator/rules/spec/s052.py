"""S052: `carriage_sequence` values that are not `1, 2, ... n` in list order.

`:583`, and the rule folds the two sentences after it. `:584` is the same
sequence continued, "and so forth"; `:589` says a carriage with no data must
still carry a valid `carriage_sequence`, and the field is `optional` with a
proto2 default of 0, so an absent value already breaks the run and a second rule
for it would report the same carriage twice. The verdict file records both as
`folded`.

**Why ERROR rather than advice, in the proto's own words.** `:585-588`: "If the
second carriage in the direction of travel has a value of 3, consumers will
discard data for all carriages". A broken run costs the whole vehicle, not the
one carriage.

**List order, not sorted order.** "The first carriage in the direction of
travel" is the first entry of the repeated field, so `1, 3, 2` is two defects
rather than a permutation that happens to contain the right numbers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.carriages import vehicle_carriages
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.carriages import VehicleCarriages
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S052"

CLAUSE = "The first carriage in the direction of travel must have a value of 1."

OUT_OF_RUN = (
    "entity ID {entity_id} carriage {ordinal} has carriage_sequence {found}, expected {expected}"
)

FIELD = "carriage_sequence"


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per carriage whose number is not its position in the run."""
    return [found for vehicle in vehicle_carriages(message, ctx) for found in _of_vehicle(vehicle)]


def _of_vehicle(vehicle: VehicleCarriages) -> list[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            OUT_OF_RUN.format(
                entity_id=vehicle.entity_id,
                ordinal=position + 1,
                found=carriage.get(FIELD),
                expected=position + 1,
            ),
            {
                ENTITY_PATH_KEY: vehicle.carriage_path(position),
                "entityId": vehicle.entity_id,
                "carriageSequence": carriage.get(FIELD),
                "expected": position + 1,
            },
        )
        for position, carriage in enumerate(vehicle.carriages)
        if carriage.get(FIELD) != position + 1
    ]
