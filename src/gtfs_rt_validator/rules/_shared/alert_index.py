"""Every Alert of a message or of a cycle, scanned once. E029, P006, P012, P015.

Four rules ask four questions of the same list. E029 asks whether a DETOUR alert
covers a vehicle's trip, P015 asks that same question for a different buffer,
P006 asks whether a NO_SERVICE alert names a cancelled trip, and P012 asks which
stops one Alert's selectors name. All four are answered by one pass over
`informed_entity`, and this module is that pass.

**It is the pass that was already here, widened.** `VehicleValidator.hasDetourAlert`
(`:242-264`) is `_shared/vehicle_bounds.has_detour_alert`, a whole-feed scan run
per failing position. That function keeps its signature and answers exactly what
it answered before this module existed; its body is now
`index_of_entities(entities).has_effect(DETOUR_EFFECT, ...)`, so there is one
traversal of the selector list in this project rather than two that have to be
kept in step. E029 is a compat byte contract, so
`tests/test_shared_alert_index.py` states the equivalence over every shape
`tests/test_shared_detour_alert.py` builds, and the differential is re-run in the
commit that touches this.

**The defaulted reads are deliberate and they are not uniform.** `hasDetourAlert`
compares `tripId.equals(selector.getTrip().getTripId())` with no `hasTripId()`
guard, so a selector carrying an empty `trip` submessage names the trip_id `""`
and matches a vehicle whose own trip_id is empty. `trip_ids` and
`trip_route_ids` reproduce that, because `has_detour_alert` is now this index
asked a question and reproducing upstream is the whole point of the compat path.
`stop_ids` and `route_ids`, which upstream never reads, use presence instead: a
selector with no `stop_id` naming `""` would put the empty string in every
Alert's stop set, and P012's question is whether an Alert names *every* stop of
a route.

**An Alert with no `effect` contributes no effect and is still an Alert.** The
`hasEffect()` guard means the proto default is never reached, so it is absent
from `trip_effects` rather than present under `UNKNOWN_EFFECT`; it is still in
`alerts`, because P012 is about selectors and does not read the effect at all.

**`DETOUR_EFFECT` stays in `vehicle_bounds.py`**, beside the comment recording
that the number is 4 under both schemas and is therefore not a mode branch, and
beside the two other things E029 needs. Importing it here would put the constant
one module further from the check that explains it, and would make this module
import the one that imports it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gtfs_rt_validator.rules._shared.memo import memoised

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, and nothing under `rules/` may import that at run time.
    from collections.abc import Sequence

    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = [
    "AlertIndex",
    "AlertSelectors",
    "cycle_index",
    "index",
    "index_of_entities",
    "visible_index",
]

_NONE: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class AlertSelectors:
    """One Alert, split by which field each of its selectors names.

    `effect` is `None` for an Alert that declares none. `role` and `path` locate
    it for an occurrence: within one message the role is the context's own, and
    within a cycle it is whichever role's file carried the Alert, which is not
    necessarily the file the rule is reporting against.
    """

    effect: int | None
    trip_ids: frozenset[str]
    trip_route_ids: frozenset[str]
    stop_ids: frozenset[str]
    route_ids: frozenset[str]
    role: str
    index: int
    path: str


@dataclass(frozen=True, slots=True)
class AlertIndex:
    """Every Alert in scope, plus the two lookups the effect questions need.

    `alerts` is in scan order, which within a message is entity order and within
    a cycle is `ROLE_ORDER` and then entity order. `stop_ids` and `route_ids`
    are the unions over `alerts`, for a rule asking whether any Alert at all
    named something.
    """

    alerts: tuple[AlertSelectors, ...]
    trip_effects: Mapping[str, frozenset[int]]
    trip_route_effects: Mapping[str, frozenset[int]]
    stop_ids: frozenset[str]
    route_ids: frozenset[str]

    def effects_for_trip(self, trip_id: str) -> frozenset[int]:
        """Every effect some Alert of this scope declares for `trip_id`."""
        return self.trip_effects.get(trip_id, _NONE)

    def has_effect(self, effect: int, trip_id: str, route_id: str | None = None) -> bool:
        """`hasDetourAlert` generalised to any effect, and exactly it for DETOUR.

        `route_id` is the *caller's* route, and the `is not None` guard is
        upstream's `routeId != null`, which comes from E029's `hasRouteId()`
        ternary rather than from anything about the selector. Passing `""` is
        therefore not the same as passing nothing: a vehicle whose descriptor
        sets `route_id` to the empty string matches every selector that names a
        trip and no route, which is upstream's behaviour.
        """
        if effect in self.trip_effects.get(trip_id, _NONE):
            return True
        return route_id is not None and effect in self.trip_route_effects.get(route_id, _NONE)


def index_of_entities(entities: Sequence[Msg], *, role: str = "") -> AlertIndex:
    """The index over one entity list, with no context and no memo.

    What `has_detour_alert` calls, so that E029's per-position scan stays a
    scan: upstream's own comment calls it expensive and caches nothing, and
    caching it here would be a behaviour this project invented for a rule whose
    contract is byte-for-byte parity.
    """
    return _scan((role, position, entity) for position, entity in enumerate(entities))


def index(message: Any, ctx: RuleContext, *, scope: str = "") -> AlertIndex:
    """The index over one message, built at most once per message.

    `scope` is `memo.py`'s: a rule reading another role's message in the same
    context passes that role as the scope, or it is served this message's index
    under somebody else's question.
    """
    return memoised(_build, message, ctx, scope=scope)


def cycle_index(ctx: RuleContext) -> AlertIndex | None:
    """Every Alert of this cycle, across every role, or `None` if there is none.

    Reads `ctx.cycle` and not `ctx.combined`, and the difference is the whole of
    what a suppressing rule needs. `combined` answers "am I the one who
    reports?", which is `_shared/crossfeed.py`'s question and is withheld from
    every message but the host's. This is the other question, "what else is in
    this cycle?", and a VehiclePositions message has every right to an answer:
    the Alert that excuses its vehicle is in a file it does not host.

    `None` therefore means there is no cycle at all rather than "not this
    cycle's host", so a caller may treat its own message as the whole scope
    without that being a guess about a file it was not shown.

    Under `--compat` there is one unnamed role whose cycle is the message
    itself, so this and `index` agree there.
    """
    cycle = ctx.cycle
    if cycle is None:
        return None
    return memoised(_build_cycle, cycle, ctx)


def visible_index(message: Any, ctx: RuleContext) -> AlertIndex:
    """Every Alert this message can legitimately see: the cycle's, or its own.

    The scope a rule wants when Alerts *suppress* its finding, which is P006 and
    P015 both. Widening the scope of a suppressor can only ever remove an
    occurrence, so the widest honest scope is the right one: an Alert in the
    `-sa` file excuses the trip whichever file the reader arrived in, and a rule
    that missed it would report a producer that had done exactly what the clause
    asks. There is nothing wider to be had, so the fallback is not a compromise:
    a context with no cycle is one message standing alone, and its own Alerts are
    then every Alert there is.

    This is not `cycle_index` plus a default, and the distinction is why the two
    exist. `cycle_index` answering `None` is a fact about the run, and a rule
    that must not guess reads it directly. `None` is *not* "I was not shown the
    cycle", which no message is any longer: `runner/context.py` puts the cycle on
    every role and withholds only the token that says which one reports for it.
    """
    scoped = cycle_index(ctx)
    return index(message, ctx) if scoped is None else scoped


def _build(message: Any, ctx: RuleContext) -> AlertIndex:
    return _scan(
        (ctx.role, position, entity) for position, entity in enumerate(message.get("entity"))
    )


def _build_cycle(cycle: Any, ctx: RuleContext) -> AlertIndex:
    return _scan(cycle.entities())


def _scan(entities: Iterable[tuple[str, int, Msg]]) -> AlertIndex:
    """The one pass. `(role, index, entity)` is `CombinedFeed.entities()`'s shape,
    so a cycle and a single message differ only in what is handed in."""
    alerts: list[AlertSelectors] = []
    trip_effects: dict[str, set[int]] = {}
    trip_route_effects: dict[str, set[int]] = {}
    for role, position, entity in entities:
        if not entity.has("alert"):
            continue
        found = _selectors_of(entity.get("alert"), role, position)
        alerts.append(found)
        if found.effect is None:
            continue
        for trip_id in found.trip_ids:
            trip_effects.setdefault(trip_id, set()).add(found.effect)
        for route_id in found.trip_route_ids:
            trip_route_effects.setdefault(route_id, set()).add(found.effect)
    return AlertIndex(
        alerts=tuple(alerts),
        trip_effects={key: frozenset(value) for key, value in trip_effects.items()},
        trip_route_effects={key: frozenset(value) for key, value in trip_route_effects.items()},
        stop_ids=frozenset().union(*(each.stop_ids for each in alerts)) if alerts else frozenset(),
        route_ids=frozenset().union(*(each.route_ids for each in alerts))
        if alerts
        else frozenset(),
    )


def _selectors_of(alert: Msg, role: str, position: int) -> AlertSelectors:
    trip_ids: set[str] = set()
    trip_route_ids: set[str] = set()
    stop_ids: set[str] = set()
    route_ids: set[str] = set()
    for selector in alert.get("informed_entity"):
        if selector.has("trip"):
            trip = selector.get("trip")
            # No `hasTripId()` or `hasRouteId()` guard, matching `:251` and
            # `:254`. See the module docstring on why this read defaults and the
            # two below do not.
            trip_ids.add(trip.get("trip_id"))
            trip_route_ids.add(trip.get("route_id"))
        if selector.has("stop_id"):
            stop_ids.add(selector.get("stop_id"))
        if selector.has("route_id"):
            route_ids.add(selector.get("route_id"))
    return AlertSelectors(
        effect=alert.get("effect") if alert.has("effect") else None,
        trip_ids=frozenset(trip_ids),
        trip_route_ids=frozenset(trip_route_ids),
        stop_ids=frozenset(stop_ids),
        route_ids=frozenset(route_ids),
        role=role,
        index=position,
        path=f"entity[{position}].alert",
    )
