"""S046: a `ReplacementStop.stop_id` that neither feed defines.

Cites `1261#1`:

> If it refers to a `Shape` entity in the real-time feed, the value of this field
> should be the one of the `stop_id` inside the entity, and _not_ the `id` of
> `FeedEntity`.

**The sentence says `Shape` and means `Stop`.** It is a copy-paste from the
identical sentence about `shape_id` at `:1202`, and `:1260` immediately above it
settles what is meant: "May refer to a new stop added using a GTFS-RT `Stop`
message in the same GTFS-RT feed, or to an existing stop defined in the (CSV)
GTFS feed's `stops.txt`." The citation quotes the proto as written, typo
included, because `tests/test_clause_citations.py` compares bytes against
`upstream/spec-clauses.json` and the index is generated from the pinned file.
Correcting it here would fail the build; correcting it there would be
hand-editing a generated artefact.

`should` is where the WARNING comes from, and it is why this rule is a warning
where S043 asking the same question of `StopSelector.stop_id` is an error: that
clause says `must`.

**Why the first citation moved.** An earlier draft quoted `:1260`, which carries
no modal verb and is therefore not in the clause index at all. `1261#1` is the
next sentence and is the same statement in the enforceable form.

**Not E011.** E011's world is `stops.txt` alone, and the whole point of this
field is that a realtime feed may define the stop itself. `rules/upstream/e011.py`
must not grow a branch for this message. The jar cannot refute that by running:
`ReplacementStop` postdates it, so it decodes the entity as unknown fields and
emits nothing at all for any fixture here.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.manifest import Severity
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.feed_index import index
from gtfs_rt_validator.rules._shared.references import STOP, stop_resolves
from gtfs_rt_validator.rules._shared.walk_trip_modifications import replacement_stops
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S046"

CLAUSE = (
    "spec: If it refers to a `Shape` entity in the real-time feed, the value of this field "
    "should be the one of the `stop_id` inside the entity, and _not_ the `id` of `FeedEntity`."
)


@rule(RULE_ID, source=CLAUSE, severity=Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Every replacement stop of every modification, flat: the grouping is S048's."""
    feed = index(message, ctx)
    for _, found in replacement_stops(message, ctx):
        if not found.stop.has("stop_id"):
            continue
        stop_id = found.stop.get("stop_id")
        if not stop_resolves(stop_id, ctx, feed):
            yield Occurrence(RULE_ID, STOP.unresolved(stop_id, feed), {ENTITY_PATH_KEY: found.path})
