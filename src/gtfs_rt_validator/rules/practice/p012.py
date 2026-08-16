"""P012: an Alert that lists every stop of a route instead of naming the route.

`:128`, "Do not apply the alert to every stop of the line." An alert that names
each stop of a line one selector at a time says nothing a consumer can act on at
the line level: it cannot tell that the whole route is affected without joining
every selector back to `stop_times.txt` itself, and an alert that gains or loses
a stop between iterations looks like a different alert. The remedy the document
asks for is one `EntitySelector` naming the `route_id`.

**The rule invents no threshold, and that is the whole of why it is safe to
ship.** It fires only on *complete* coverage of a route's stop set, which is the
exact shape the sentence forbids, and never on "many stops of a route". "Many"
would be a number this project chose and published under somebody else's
citation, and that is why the five Best Practices statements giving no threshold
of their own are rejected outright rather than given one here: they are the R4
group of `upstream/practice-clause-verdicts.json`. Complete coverage needs no
number.

**"Names that route" means `EntitySelector.route_id` and not
`EntitySelector.trip.route_id`.** The clause's subject is the *line*, and the
line selector is the route one; a trip selector scopes an alert to one run of the
line, which is a narrower claim than the one the clause asks for and is not the
remedy it proposes. This also keeps the rule on the presence-guarded half of
`_shared/alert_index.py`: `route_ids` and `stop_ids` are built with `has()`
because upstream never reads them, while `trip_ids` and `trip_route_ids`
reproduce `hasDetourAlert`'s defaulted read, under which an empty `trip {}`
submessage names the route `""`. A rule reading the defaulted set would treat
that submessage as naming every route it was asked about.

An `informed_entity` with an explicitly blank `stop_id` therefore names the stop
`""`, which is a stop_id no route serves, rather than naming nothing.

**A route whose trips serve no stops cannot be covered.**
`static/_tables.build_route_stop_ids` leaves such a route out of the mapping
instead of mapping it to an empty frozenset, and the reason is this rule: every
set contains the empty set, so an empty route would make every alert in the feed
a violation. The mapping's contract is what stops that, and
`tests/test_rule_p012.py` pins it from this side as well.

**Under a 2015 decode the fixture is fully visible.** `Alert`,
`EntitySelector.stop_id` and `EntitySelector.route_id` are all 2015 fields, so
the jar reads such a message whole and still reports nothing: none of the 56 asks
a route which stops it serves, which is why `OVERLAP` in
`tests/test_tier_overlap.py` names no neighbour for P012 and why
`StaticContext.route_stop_ids` has no `GtfsMetadata` counterpart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.alert_index import index
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.alert_index import AlertSelectors
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P012"

CLAUSE = "Do not apply the alert to every stop of the line."

COVERED = (
    "alert names all {count} stops served by route_id {route_id} as stop selectors and does not "
    "name the route itself"
)


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per covered route, per Alert.

    The scope is this message rather than the cycle: an `informed_entity` list is
    entirely local to one Alert, so the pass that answers this is
    `alert_index.index` and the path it attaches is this message's own. An alert
    covering two routes is two instances of the shape the clause forbids, and
    the routes are reported in id order so which one comes first does not depend
    on `trips.txt` row order.
    """
    served = ctx.static.route_stop_ids
    return [
        _found(alert, route_id, served[route_id])
        for alert in index(message, ctx).alerts
        if alert.stop_ids
        for route_id in sorted(served)
        if route_id not in alert.route_ids and served[route_id] <= alert.stop_ids
    ]


def _found(alert: AlertSelectors, route_id: str, stop_ids: frozenset[str]) -> Occurrence:
    return Occurrence(
        RULE_ID,
        COVERED.format(count=len(stop_ids), route_id=route_id),
        {ENTITY_PATH_KEY: alert.path, "routeId": route_id},
    )
