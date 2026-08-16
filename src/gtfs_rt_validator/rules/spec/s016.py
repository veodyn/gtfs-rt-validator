"""S016: a `TripProperties.shape_id` that names no shape anywhere.

`:410-414` says `shape_id` "can refer to a shape defined in the (CSV) GTFS in
shapes.txt or a `Shape` in the same (protobuf) real-time feed", and the sentence
this rule cites says which value to write when it is the second: the `shape_id`
inside the entity, never the `FeedEntity.id` wrapping it. So a value that
resolves to neither place is either a shape nobody defined or that exact
mistake, and the rule says which, because a bare "unresolvable" would waste the
one thing the clause bothered to warn about.

**The `-ignoreShapes` gate, which every later shape rule copies, and the two
states it used to swallow.** `ctx.static.shape_points` is empty for three
different reasons: `-ignoreShapes`, an archive that ships no `shapes.txt`
(`static/adapter.py:81` lists it among two `OPTIONAL_TABLES`), and
`GtfsMetadata`'s four-point gate in `_tables.build_shapes`. Returning early on
all three was one decision too broad, and a codex audit found it. Only the first
is a state where the static half of the resolution cannot be asked; in the other
two `shapes.txt` was read and declares exactly the ids it declares, so a value
that is not among them really is not among them. The other two were a false
negative of both halves of this rule, the entity-id half worst of all, because
that half is what the cited sentence is about and it never needed `shapes.txt`.

So the early return is `shapes_withheld`, and the resolution reads `shape_ids`
rather than `shape_points`. The two are not the same question: `shape_points` is
gated at three points feed-wide for `GtfsMetadata.java:127` parity, which is
right for the geometry the 56 read and wrong for "which ids does this feed
declare", and a three-point shape is a perfectly good shape. `shape_ids` is read
before that gate. Both members are documented in `static/context.py` and no
compat rule may read either.

Nothing upstream reads `TripProperties`, which the 2015 descriptor does not
carry, so there is no overlap to respect here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.feed_index import index
from gtfs_rt_validator.rules._shared.walk_entities import entities
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.feed_index import FeedIndex
    from gtfs_rt_validator.rules._shared.walk_entities import EntityRecord
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S016"

CLAUSE = (
    "If it refers to a `Shape` entity in the same real-time feed, the value of this field "
    "should be the one of the `shape_id` inside the entity, and _not_ the `id` of `FeedEntity`."
)

UNRESOLVED = (
    "trip_id {trip_id} shape_id {shape_id} is in neither shapes.txt nor a Shape entity of this feed"
)

ENTITY_ID_WRITTEN = (
    "trip_id {trip_id} shape_id {shape_id} is a FeedEntity id, not the shape_id inside it"
)


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """Every TripUpdate whose `trip_properties` names a shape nothing defines."""
    if ctx.static.shapes_withheld:
        return None
    defined = index(message, ctx)
    return [
        found
        for record in entities(message, ctx).carrying("trip_update")
        for found in _of(record, ctx, defined)
    ]


def _of(record: EntityRecord, ctx: RuleContext, defined: FeedIndex) -> list[Occurrence]:
    """At most one occurrence, so the walk above stays one comprehension."""
    trip_update = record.entity.get("trip_update")
    properties = trip_update.get("trip_properties")
    if not properties.has("shape_id"):
        return []
    shape_id = properties.get("shape_id")
    if shape_id in ctx.static.shape_ids or defined.defines_shape(shape_id):
        return []
    template = ENTITY_ID_WRITTEN if shape_id in defined.entity_ids else UNRESOLVED
    trip_id = trip_update.get("trip").get("trip_id")
    return [
        Occurrence(
            RULE_ID,
            template.format(trip_id=trip_id, shape_id=shape_id),
            {
                ENTITY_PATH_KEY: f"{record.path}.trip_update.trip_properties",
                "shapeId": shape_id,
                "tripId": trip_id,
            },
        )
    ]
