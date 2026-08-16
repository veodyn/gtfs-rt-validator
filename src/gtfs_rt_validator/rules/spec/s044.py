"""S044: a `SelectedTrips.shape_id` that neither feed defines.

Cites `1202#1`, on `TripModifications.SelectedTrips.shape_id`:

> If it refers to a `Shape` entity in the real-time feed, the value of this field
> should be the one of the `shape_id` inside the entity, and _not_ the `id` of
> `FeedEntity`.

`should` is where the WARNING comes from. It is the same sentence S016 cites for
`TripProperties.shape_id` and, with `stop_id` substituted, the one S046 cites, so
all three resolve a realtime-or-static reference the same way through
`_shared/references.py`.

**The clause is about one substitution, so the occurrence names it.** A bare
"unresolvable" would be a correct report of a superset and would waste the
finding the sentence was written for, so when the value is a `FeedEntity.id` of
this message the occurrence says so. `_shared/feed_index.py` keeps `entity_ids`
for exactly this, and it is the reason that field is in the index at all.

**The `-ignoreShapes` gate, and it is not optional. But it is only that flag.**
Reading a `shape_points` the flag emptied would report every `shape_id` in the
feed as unresolvable, which is the shape of the bug that made E029 vanish
silently under the same flag. Two other states empty `shape_points` and are not
that bug: an archive with no `shapes.txt`, one of `static/adapter.py`'s two
optional tables, where no static shape id exists at all; and a `shapes.txt`
below `GtfsMetadata.java:127`'s four-point gate, where the ids were read and the
geometry was dropped. Returning early on all three was one decision too broad,
and a codex audit found it: in both of those the answer is known, and the
entity-id substitution the cited sentence is actually about never needed
`shapes.txt` in the first place.

So the early return is `ctx.static.shapes_withheld`, the one state where nothing
was read, and the resolution reads `ctx.static.shape_ids`, which is the id
column before the compat gate. That gate stays where it is: it is
`GtfsMetadata` parity and the 56 depend on it. S016 makes the same two moves for
`TripProperties.shape_id` and its docstring carries the same argument.

`TripModifications` postdates the jar, so no differential can confirm this rule
or refute the claim that no upstream rule borders it: `OVERLAP` in
`tests/test_tier_overlap.py` names no neighbour for S044.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.manifest import Severity
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.feed_index import index
from gtfs_rt_validator.rules._shared.references import SHAPE
from gtfs_rt_validator.rules._shared.walk_trip_modifications import trip_modifications
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S044"

CLAUSE = (
    "spec: If it refers to a `Shape` entity in the real-time feed, the value of this field "
    "should be the one of the `shape_id` inside the entity, and _not_ the `id` of `FeedEntity`."
)


@rule(RULE_ID, source=CLAUSE, severity=Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Every `SelectedTrips` of every `TripModifications`, shapes permitting."""
    if ctx.static.shapes_withheld:
        return
    feed = index(message, ctx)
    for record in trip_modifications(message, ctx):
        for position, selected in enumerate(record.owner.get("selected_trips")):
            if not selected.has("shape_id"):
                continue
            shape_id = selected.get("shape_id")
            if shape_id in ctx.static.shape_ids or feed.defines_shape(shape_id):
                continue
            yield Occurrence(
                RULE_ID,
                SHAPE.unresolved(shape_id, feed),
                {ENTITY_PATH_KEY: f"{record.path}.selected_trips[{position}]"},
            )
