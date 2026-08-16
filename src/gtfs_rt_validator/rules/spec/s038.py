"""S038: a realtime `Shape` claiming a shape_id the static feed already defines.

`Shape.shape_id`'s comment, at `:1104`:

    Must be different than any shape_id defined in the (CSV) GTFS.

The `Shape` message exists for paths that are *not* in the static feed, a detour
being the example the message comment gives. Reusing a static id makes the
reference ambiguous: `TripProperties.shape_id` and `SelectedTrips.shape_id` both
resolve against `shapes.txt` or against a realtime `Shape`, so an id that is both
resolves two ways and a consumer picks one.

**It reads `shape_ids`, not `shape_points`, and the difference is the whole
point.** `shape_points` is the structure the 56 read, and it is gated:
`GtfsMetadata.java:127`'s feed-wide `shapePoints != null && !ignoreShapes &&
shapePoints.size() > 3` empties it for a feed of three shape points or fewer, so
under compat a three-point `shapes.txt` is a feed with no shapes at all. That is
a byte contract and `static/_tables.py` keeps it. It is the wrong source for this
rule twice over: a three-point shape is perfectly valid, and the collision the
clause forbids is a collision of *ids*, not of geometry, so a shape whose
polyline the gate dropped still owns its id. `StaticContext.shape_ids` is the
same table read before the gate, and this is the question it exists for.

**Under `-ignoreShapes` this rule can still only under-report, and there is no
early return.** That flag empties `RawTables.shapes` at the loader, so `shape_ids`
is empty too and nothing collides. Nothing in a run can tell that from a feed
that genuinely defines no shapes, so the honest behaviour is the one an empty
table produces: no collisions, no findings, a false negative and never a false
positive. That is the opposite direction from S016, which reads the same table to
decide a reference is *unresolvable* and must return early or report every
reference in the feed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_entities import entities
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S038"

CLAUSE = "spec: Must be different than any shape_id defined in the (CSV) GTFS."

SHAPE = "shape"
SHAPE_ID = "shape_id"


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"entity ID {record.entity_id} {SHAPE_ID} {shape.get(SHAPE_ID)} "
            f"is already defined in the GTFS shapes.txt",
            {ENTITY_PATH_KEY: f"{record.path}.{SHAPE}"},
        )
        for record in entities(message, ctx).carrying(SHAPE)
        for shape in [record.entity.get(SHAPE)]
        if shape.has(SHAPE_ID) and shape.get(SHAPE_ID) in ctx.static.shape_ids
    ]
