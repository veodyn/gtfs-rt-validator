"""The one pass `CrossFeedDescriptorValidator` makes, read by W003 and E047.

`CrossFeedDescriptorValidator.java:80-116` walks the combined feed once and
fills six containers; `:125-164` then runs W003's four loops off them and calls
E047's two halves from inside the first two. This project puts each reported id
in its own module, so the pass lives here and both modules read it, the same
arrangement `_shared/walks.py` makes for the stateful loops. Unlike a walk this
yields no events: the two rules do not interleave in the output, because
upstream collects them into two lists and emits W003's whole group before
E047's (`:166-171`).

**Two early returns, and the one that is not written down.** `validate` returns
empty when `combinedFeedMessage == null` (`:50-53`), which here is
`ctx.combined is None` on every message but its cycle's host. That is the
*reporting* view and it is deliberately not `ctx.cycle`, which every role gets:
these two rules emit one finding per cycle, and a rule that merely reads what is
beside it uses the other one. It returns empty again when
`tripUpdateCount == 0 || vehiclePositionCount
== 0` (`:119-122`). `BatchProcessor` adds a third by only passing a combined
message when `GtfsUtils.isCombinedFeed` is true (`BatchProcessor.java:248-253`),
which needs one `FeedMessage` carrying more than one of TripUpdate,
VehiclePosition and Alert. That third gate is **not reproduced, because it
cannot change an answer**: reaching any occurrence needs both counts non-zero,
which needs a TripUpdate entity and a VehiclePosition entity in the same
combined view, which is already two entity types. Implementing it would add a
scan whose result is implied by the one below it.

**The counts are of presence, not of usable ids.** `hasTripId` and
`hasVehicleId` (`:181-193`) test `hasTrip() && getTrip().hasTripId()` and
`hasVehicle() && getVehicle().hasId()`, and protobuf presence is true for an
explicitly set `""`. Both counts increment *before* the `StringUtils.isEmpty`
test that decides between a map and a set, so a feed whose every id is the empty
string still gets past the gate and puts `""` in both sets. That is what
`CrossFeedDescriptorValidatorTest.java:122-157` and `:289-422` exist to pin.

**Two of the four maps collapse differently.** Every `put` is last-write-wins on
its own key, and the two TripUpdates maps are keyed on different fields
(`:93-94`), so two TripUpdates sharing a vehicle_id keep both entries in the
trip-keyed map and one in the vehicle-keyed one.

**Only four of the six containers are iterated**, and only those are put into
Java hash order here; `rules/_shared/javahash.py` names the four sites and says
why the other two need nothing. Ordering at build time rather than at each use
means the order is computed once for the two rules that share it, and means a
rule cannot forget to ask for it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gtfs_rt_validator.rules._shared.javahash import iteration_order

if TYPE_CHECKING:  # Type-only: nothing under `rules/` may import the runner at
    # run time, since that reaches the static layer and the sibling package.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["MEMO_KEY", "CrossFeedIndex", "index_for"]

#: Where the built index sits on `ctx.memo`. Namespaced like a walk's key, so a
#: rule caching something of its own under a plain name cannot land on it.
MEMO_KEY = "crossfeed:index"


@dataclass(frozen=True, slots=True)
class CrossFeedIndex:
    """Upstream's six containers, under upstream's own names in snake_case.

    The two maps and two sets that upstream iterates are in Java hash iteration
    order; the two it reaches only through `containsKey` and `get` are in
    insertion order, which is not observable and is not simulated.
    """

    trip_updates_trip_to_vehicle: dict[str, str]
    trip_updates_vehicle_to_trip: dict[str, str]
    trips_without_vehicles: tuple[str, ...]
    vehicle_positions_vehicle_to_trip: dict[str, str]
    vehicle_positions_trip_to_vehicle: dict[str, str]
    vehicles_without_trips: tuple[str, ...]


def index_for(ctx: RuleContext) -> CrossFeedIndex | None:
    """The index for this message's cycle, or `None` where upstream returns early.

    Memoised on `ctx.memo`, which the runner builds fresh per message, so the
    two rules that read it walk the cycle once between them. `None` is memoised
    as well: it is an answer, and recomputing it would walk every entity again
    for the second rule.
    """
    if MEMO_KEY in ctx.memo:
        return ctx.memo[MEMO_KEY]
    built = _build(ctx)
    ctx.memo[MEMO_KEY] = built
    return built


def _build(ctx: RuleContext) -> CrossFeedIndex | None:
    combined = ctx.combined
    if combined is None:
        return None

    trip_to_vehicle: dict[str, str] = {}
    vehicle_to_trip: dict[str, str] = {}
    trips_without_vehicles: dict[str, None] = {}
    trip_update_count = 0

    vp_vehicle_to_trip: dict[str, str] = {}
    vp_trip_to_vehicle: dict[str, str] = {}
    vehicles_without_trips: dict[str, None] = {}
    vehicle_position_count = 0

    for _role, _index, entity in combined.entities():
        if entity.has("trip_update"):
            trip_update = entity.get("trip_update")
            trip_id = _nested(trip_update, "trip", "trip_id")
            if trip_id is not None:
                trip_update_count += 1
                vehicle_id = _nested(trip_update, "vehicle", "id") or ""
                if not vehicle_id:
                    trips_without_vehicles[trip_id] = None
                else:
                    trip_to_vehicle[trip_id] = vehicle_id
                    vehicle_to_trip[vehicle_id] = trip_id
        if entity.has("vehicle"):
            position = entity.get("vehicle")
            vehicle_id = _nested(position, "vehicle", "id")
            if vehicle_id is not None:
                vehicle_position_count += 1
                trip_id = _nested(position, "trip", "trip_id") or ""
                if not trip_id:
                    vehicles_without_trips[vehicle_id] = None
                else:
                    vp_vehicle_to_trip[vehicle_id] = trip_id
                    vp_trip_to_vehicle[trip_id] = vehicle_id

    if trip_update_count == 0 or vehicle_position_count == 0:
        return None

    return CrossFeedIndex(
        trip_updates_trip_to_vehicle=_in_java_order(trip_to_vehicle),
        trip_updates_vehicle_to_trip=vehicle_to_trip,
        trips_without_vehicles=iteration_order(trips_without_vehicles),
        vehicle_positions_vehicle_to_trip=_in_java_order(vp_vehicle_to_trip),
        vehicle_positions_trip_to_vehicle=vp_trip_to_vehicle,
        vehicles_without_trips=iteration_order(vehicles_without_trips),
    )


def _nested(message: Msg, descriptor: str, field: str) -> str | None:
    """`hasX() && getX().hasY() ? getX().getY() : null`, in one place.

    `None` is absent, which is the branch `hasTripId` and `hasVehicleId` guard;
    `""` is present and blank, which they let through and `StringUtils.isEmpty`
    catches later. Collapsing the two here would lose the distinction upstream's
    tests exist to pin.
    """
    if not message.has(descriptor):
        return None
    inner = message.get(descriptor)
    if not inner.has(field):
        return None
    return inner.get(field)


def _in_java_order(mapping: Mapping[str, str]) -> dict[str, str]:
    """The same entries, iterating as `HashMap.entrySet()` would.

    A Python `dict` already reproduces Java's *insertion* semantics, including
    a repeated key keeping its first position, so only the bucket walk is left
    to apply.
    """
    return {key: mapping[key] for key in iteration_order(mapping)}
