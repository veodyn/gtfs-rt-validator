"""S047: a replacement stop that is not a routable stop.

Cites `1261#2`, the last sentence of the `ReplacementStop.stop_id` comment:

> The replacement stop MUST have `location_type=0` (routable stops).

Capital `MUST` is where the ERROR comes from. A modified trip that lists a
station, an entrance or a boarding area among its stops names something no
vehicle can serve.

**Only a stop `stops.txt` defines has a location type to read.** The pinned
`Stop` message has fourteen fields and `location_type` is not one of them, so a
replacement stop the realtime feed defines carries no location type at all and is
taken as routable here. That is the only answer available without inventing a
value the proto does not carry, and `tests/test_rule_s047.py` asserts the absence
against `schema_current` so a field added at a later pin fails rather than being
quietly ignored. `_shared/feed_index.py` records the same fact on its `stops`
index.

**A stop_id that resolves nowhere is S046's finding, not this one.** It has no
location type by either route, and charging one mistake to two clauses is the
double-reporting `tests/test_tier_overlap.py` exists to prevent.

E015 is this predicate on `StopTimeUpdate.stop_id`, a different message it cannot
reach. `ReplacementStop` postdates the jar, so the differential can neither
confirm this rule nor refute that boundary.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.manifest import Severity
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_trip_modifications import replacement_stops
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S047"

CLAUSE = "spec: The replacement stop MUST have `location_type=0` (routable stops)."

#: What the clause requires, and the only value `stops.txt` may give a stop this
#: rule accepts.
ROUTABLE = 0


@rule(RULE_ID, source=CLAUSE, severity=Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Every replacement stop that resolves statically, and its location type.

    `.get` answering `None` covers both cases at once: a stop_id `stops.txt`
    does not carry, which is S046's finding, and a stop this feed defined
    itself, which has no location type to read. Neither is reported here.
    """
    location_types = ctx.static.stop_location_types
    for _, found in replacement_stops(message, ctx):
        if not found.stop.has("stop_id"):
            continue
        stop_id = found.stop.get("stop_id")
        location_type = location_types.get(stop_id)
        if location_type is not None and location_type != ROUTABLE:
            yield Occurrence(
                RULE_ID,
                f"stop_id {stop_id} has location_type {location_type}, not 0",
                {ENTITY_PATH_KEY: found.path},
            )
