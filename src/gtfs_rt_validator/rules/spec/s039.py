"""S039: a `Shape` entity that draws nothing.

`Shape.encoded_polyline`'s comment, at `:1112`, which is `shape_id`'s sentence
repeated on the other field:

    This field is required as per reference.md, but needs to be specified here
    optional because "Required is Forever"

S037's docstring makes the argument for reading the comment rather than the wire
cardinality, and it applies here unchanged. A `Shape` with no polyline is a
detour with no path: `TripProperties.shape_id` may resolve to it and a consumer
that follows the reference finds nothing to draw.

An `encoded_polyline` written as the empty string is present, so this rule is
silent on it. That feed is S040's finding, a polyline with fewer than two
points, and reporting it here as well would say the same thing twice about one
shape.
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

RULE_ID = "S039"

CLAUSE = (
    "spec: This field is required as per reference.md, but needs to be specified here "
    'optional because "Required is Forever"'
)

SHAPE = "shape"
POLYLINE = "encoded_polyline"


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"entity ID {record.entity_id} {SHAPE} has no {POLYLINE}",
            {ENTITY_PATH_KEY: f"{record.path}.{SHAPE}"},
        )
        for record in entities(message, ctx).carrying(SHAPE)
        if not record.entity.get(SHAPE).has(POLYLINE)
    ]
