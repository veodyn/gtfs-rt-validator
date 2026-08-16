"""S037: a `Shape` entity that does not say which shape it is.

`Shape.shape_id`'s comment, at `:1105`:

    This field is required as per reference.md, but needs to be specified here
    optional because "Required is Forever"

The comment is the normative source **because** the wire format cannot be. The
field is declared `optional` and the sentence explains that proto2's promotion
rules are the only reason, so a validator reading the cardinality off the wire
would enforce the opposite of what the file says.

Without the id, nothing can reference the shape: `TripProperties.shape_id` and
`SelectedTrips.shape_id` both resolve to "the `shape_id` inside the entity, and
_not_ the `id` of `FeedEntity`", so an unnamed `Shape` is unreachable however
well formed its polyline is. `_shared/feed_index.py` declines to index one for
the same reason, which is why this rule reads the entity list rather than the
index.

S039 cites the identical sentence on `encoded_polyline`. Two clause ids, two
lines, two fields, two rules.
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

RULE_ID = "S037"

CLAUSE = (
    "spec: This field is required as per reference.md, but needs to be specified here "
    'optional because "Required is Forever"'
)

SHAPE = "shape"
SHAPE_ID = "shape_id"


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"entity ID {record.entity_id} {SHAPE} has no {SHAPE_ID}",
            {ENTITY_PATH_KEY: f"{record.path}.{SHAPE}"},
        )
        for record in entities(message, ctx).carrying(SHAPE)
        if not record.entity.get(SHAPE).has(SHAPE_ID)
    ]
