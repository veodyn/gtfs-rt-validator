"""S040: an encoded_polyline that draws fewer than two points, or none at all.

`Shape.encoded_polyline`'s comment, at `:1110`:

    This polyline must contain at least two points and represent the full shape
    of the trip where it's used.

**Only the first half is enforced.** "Represent the full shape of the trip" is
rejected under R2, producer intent the feed does not record: two byte-identical
polylines satisfy and violate it depending on a trip nothing here can see. The
verdict file records this rule as `rule_in_part` for that reason.

One point is a location, not a path, so a shape carrying fewer than two draws
nothing a consumer can follow. A string that does not decode at all is reported
too, and with the decoder's own reason: `_shared/polyline.py` answers a
`Polyline` carrying whatever decoded plus why it stopped, never an exception,
because a malformed feed is the input this project exists to describe.

An `encoded_polyline` that was never written is S039's finding, not this one.
The empty string *was* written, so S039 is silent on it and it lands here as
zero points.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.polyline import Polyline, polyline
from gtfs_rt_validator.rules._shared.walk_entities import entities
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S040"

CLAUSE = (
    "spec: This polyline must contain at least two points and represent the full shape "
    "of the trip where it's used."
)

SHAPE = "shape"
POLYLINE = "encoded_polyline"

#: What the clause asks for, spelled once.
MINIMUM_POINTS = 2


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"entity ID {record.entity_id} {POLYLINE} {_fault(decoded)}",
            {ENTITY_PATH_KEY: f"{record.path}.{SHAPE}"},
        )
        for record in entities(message, ctx).carrying(SHAPE)
        for shape in [record.entity.get(SHAPE)]
        if shape.has(POLYLINE)
        for decoded in [polyline(shape.get(POLYLINE), ctx)]
        if decoded.error is not None or len(decoded.points) < MINIMUM_POINTS
    ]


def _fault(decoded: Polyline) -> str:
    """Why this polyline fails the clause: it broke, or it is too short."""
    if decoded.error is not None:
        return f"does not decode: {decoded.error}"
    count = len(decoded.points)
    return f"decodes to {count} point{'' if count == 1 else 's'}, and at least two are required"
