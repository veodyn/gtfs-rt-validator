"""S030: an EntitySelector naming a direction with no route to take it on.

`EntitySelector.direction_id`'s comment, at `:996`:

    If provided the route_id must also be provided.

A `direction_id` is 0 or 1 within one route's `trips.txt` rows and means nothing
on its own, so a selector naming a direction and no route selects every inbound
trip of every route in the feed, which is not what any producer means.

**Not E033, and the band is disjoint.** E033 asks whether a selector specifies
anything at all, and its list is `agency_id`, `route_id`, `route_type` and
`stop_id`: `direction_id` is not on it and neither is `trip`. So a selector
carrying a `stop_id` and a `direction_id` satisfies E033 and violates this
clause, which is the fixture that separates the two. A selector carrying only a
`direction_id` violates both, and both report it; that overlap is the declared
one, recorded as E033 in `OVERLAP` in `tests/test_tier_overlap.py`.

**Presence, not truth.** `direction_id` is a `uint32` whose meaningful values
include 0, so a rule reading truthiness would pass over every inbound selector
in every feed.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_entities import entities
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S030"

CLAUSE = "spec: If provided the route_id must also be provided."

ALERT = "alert"
SELECTORS = "informed_entity"
DIRECTION = "direction_id"
ROUTE = "route_id"


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        occurrence
        for record in entities(message, ctx).carrying(ALERT)
        for occurrence in _routeless(record.entity.get(ALERT), record.entity_id, record.path)
    ]


def _routeless(alert: Msg, entity_id: str, path: str) -> Iterator[Occurrence]:
    for index, selector in enumerate(alert.get(SELECTORS)):
        if selector.has(DIRECTION) and not selector.has(ROUTE):
            yield Occurrence(
                RULE_ID,
                f"alert ID {entity_id} {SELECTORS}[{index}] sets "
                f"{DIRECTION} {selector.get(DIRECTION)} without {ROUTE}",
                {ENTITY_PATH_KEY: f"{path}.{ALERT}.{SELECTORS}[{index}]"},
            )
