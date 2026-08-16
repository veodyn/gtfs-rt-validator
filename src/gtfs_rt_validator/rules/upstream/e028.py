"""E028: a vehicle position outside the agency's coverage area.

Ported from `validation/rules/VehicleValidator.java:164-190` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. The check picks a bounding box,
asks whether the position is inside it, and reports when it is not. It is
reached only for a position that is present, complete and inside the world,
because it is the `else` of E026's two branches; and its answer gates E029.
Both facts belong to the loop, which is `_shared/walk_vehicle.py`.

**Which box, and the word for it, are the same decision.**
`getShapeBoundingBoxWithBuffer()` wins whenever it is non-null and the
occurrence says `shapes.txt`; otherwise the box is the stops box and the
occurrence says `stops.txt`. It is null in three cases, all of which
`GtfsMetadata.java:127` collapses into one condition: no `shapes.txt` at all,
`-ignoreShapes`, and a feed-wide shape point count of three or fewer. The gate
is `shapePoints.size() > 3`, so **four points open it**. That is an output-byte
difference and not merely a sensitivity one, which is why
`tests/test_rule_e028.py` asserts the word as well as the count.

The buffered boxes are `StaticContext`'s, built by `geometry/bbox.py`, which
reproduces spatial4j 0.6 including its asymmetric buffer and its all-NaN box
over a feed with no coordinates. Nothing is recomputed here. The box choice and
the occurrence text live in `_shared/vehicle_bounds.py`, next to E029's, since
the two share the position rendering and the mile conversion.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.walk_vehicle import vehicles
from gtfs_rt_validator.rules._shared.walks import events_for
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "E028"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """This rule's share of the one `VehicleValidator` pass, in entity order."""
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, vehicles, message, ctx)
    ]
