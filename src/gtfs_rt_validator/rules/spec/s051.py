"""S051: two `CarriageDetails` of one VehiclePosition sharing an `id`.

`:563`, "Should be unique per vehicle", a WARNING because the sentence says
`should`. "per vehicle" is the whole scope: two vehicles may each carry a
carriage called `1`, and `_shared/carriages.py` groups by the VehiclePosition
that declares them so the comparison cannot leak across vehicles.

**A carriage that declares no `id` is not a carriage called "".** The field is
`optional`, so `has("id")` is the question, and two carriages that both omit it
have omitted it rather than agreed on a value. An id explicitly written as the
empty string is present and does collide with another empty one, which is the
same presence-not-truth distinction E039 turns on.

Not E052, which reports a `VehicleDescriptor.id` shared by two vehicles in one
message. Different field, different message, and neither implies the other.
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

RULE_ID = "S051"

CLAUSE = "Should be unique per vehicle."

SHARED = "entity ID {entity_id} carriage id {carriage_id} is claimed by {count} carriages"


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per id more than one carriage of one vehicle declares."""
    return [found for vehicle in vehicle_carriages(message, ctx) for found in _of_vehicle(vehicle)]


def _of_vehicle(vehicle: VehicleCarriages) -> list[Occurrence]:
    positions: dict[str, list[int]] = {}
    for position, carriage in enumerate(vehicle.carriages):
        if carriage.has("id"):
            positions.setdefault(carriage.get("id"), []).append(position)
    return [
        Occurrence(
            RULE_ID,
            SHARED.format(entity_id=vehicle.entity_id, carriage_id=carriage_id, count=len(indexes)),
            {
                ENTITY_PATH_KEY: vehicle.path,
                "entityId": vehicle.entity_id,
                "carriageId": carriage_id,
                "carriageIndexes": indexes,
            },
        )
        for carriage_id, indexes in positions.items()
        if len(indexes) > 1
    ]
