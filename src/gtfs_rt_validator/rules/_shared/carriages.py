"""One pass over the `multi_carriage_details` of every VehiclePosition.

Two rules read it and neither may loop on its own: S051 asks whether two
carriages of one vehicle share an `id`, S052 whether the `carriage_sequence`
values run `1, 2, ... n` in list order. Both need the carriages grouped by the
vehicle that carries them, because "per vehicle" is the scope of one clause and
"the first carriage in the direction of travel" is the scope of the other, so a
flat stream of carriages would lose exactly what both are about.

The walk yields one record per VehiclePosition *entity*, including the ones with
no carriages at all: a rule that wants only the populated ones filters, and a
rule that wants to say something about an empty list can. `memo.py` says where
the once is kept.

This walk was not one of the six the tier was designed around. It is here rather
than in either rule because shared logic lives in `rules/_shared/` and is never
copy-pasted, and two rules is what makes it shared.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.rules._shared.memo import memoised

if TYPE_CHECKING:  # Type-only: nothing under `rules/` may import the runner at
    # run time, because it reaches the static layer and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["FIELD", "VehicleCarriages", "vehicle_carriages"]

#: The repeated field both rules walk, named once so neither spells it.
FIELD = "multi_carriage_details"


@dataclass(frozen=True, slots=True)
class VehicleCarriages:
    """One VehiclePosition and the carriages it declares, in list order."""

    entity_index: int
    entity_id: str
    position: Msg
    carriages: tuple[Msg, ...]
    path: str

    def carriage_path(self, position: int) -> str:
        """Where one carriage sits, for an occurrence's `entityPath`."""
        return f"{self.path}.{FIELD}[{position}]"


def vehicle_carriages(message: Any, ctx: RuleContext) -> tuple[VehicleCarriages, ...]:
    """Every VehiclePosition of `message`, walked at most once per context."""
    return memoised(_build, message, ctx)


def _build(message: Any, ctx: RuleContext) -> tuple[VehicleCarriages, ...]:
    return tuple(
        VehicleCarriages(
            entity_index=index,
            entity_id=entity.get("id"),
            position=entity.get("vehicle"),
            carriages=tuple(entity.get("vehicle").get(FIELD)),
            path=f"entity[{index}].vehicle",
        )
        for index, entity in enumerate(message.get("entity"))
        if entity.has("vehicle")
    )
