"""Which realtime `Shape` a trip claims, and the points it decodes to. P015.

The pinned proto lets a feed publish geometry of its own: a `Shape` entity
carries a `shape_id` and an `encoded_polyline`, and a trip reaches one through
`TripUpdate.TripProperties.shape_id` or through
`TripModifications.SelectedTrips`. **Neither `VehiclePosition` nor
`TripDescriptor` carries a `shape_id`**, so a rule holding a vehicle's trip_id
cannot get from it to a realtime shape without this join, which is the whole
reason the module exists rather than the lookup sitting in the rule.

E029 cannot use any of this. `Shape` postdates the 2015 schema the compat path
decodes with, so `getBufferedTripShape` reads `shapes.txt` and nothing else, and
nothing here is on the compat path or may come to be.

**One pass, resolved afterwards.** A `Shape` entity may sit before or after the
TripUpdate that names it and a feed is under no obligation to order them, so the
published shapes and the claims on them are collected separately and joined at
the end.

**Points come out as `(lon, lat)`.** `_shared/polyline` answers
`(latitude, longitude)`, which is the encoding's own order, and every geometric
thing in this project is `(lon, lat)`: `geometry/buffer.within_buffered_shape`,
`static/_tables.Point` and `_shared/geodesic`. The swap happens here, once.

**A polyline that stopped early is skipped rather than used as far as it got.** A
truncated path is not the trip's path, and the broken string is S040's finding
rather than a geometry to measure against.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gtfs_rt_validator.rules._shared.memo import memoised
from gtfs_rt_validator.rules._shared.polyline import polyline

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, and nothing under `rules/` may import that at run time.
    from collections.abc import Iterable

    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["Points", "shapes_by_trip"]

#: One shape's points, `(lon, lat)` degrees, in the order the polyline carried.
Points = tuple[tuple[float, float], ...]


def shapes_by_trip(message: Any, ctx: RuleContext) -> dict[str, Points]:
    """`trip_id` to the points of the `Shape` that trip claims, built once.

    Over the cycle wherever the context has one, from **every** role of it: a
    `Shape` published in the TripUpdates file is the geometry of that trip
    whichever file the vehicle riding it arrived in. So this reads `ctx.cycle`
    rather than `ctx.combined`, which is withheld from every message but the
    cycle's host and answers a question about reporting rather than about
    reading. A context with no cycle at all is one message standing alone, and
    scanning it is then the complete answer rather than a partial one.

    Under `--compat` there is one role and the two agree, though no compat rule
    reads this.
    """
    cycle = ctx.cycle
    if cycle is None:
        return memoised(_build, message, ctx)
    return memoised(_build_cycle, cycle, ctx)


def _build(message: Any, ctx: RuleContext) -> dict[str, Points]:
    return _scan(message.get("entity"), ctx)


def _build_cycle(cycle: Any, ctx: RuleContext) -> dict[str, Points]:
    return _scan((entity for _, _, entity in cycle.entities()), ctx)


def _scan(entities: Iterable[Msg], ctx: RuleContext) -> dict[str, Points]:
    """The one pass. A claim on a shape nobody published resolves to nothing.

    So does a claim on a shape that decoded to **no points**, which the
    truthiness test at the end is doing on purpose: the empty string is a clean
    decode of zero points rather than a failure, but zero points is not a path,
    and a caller left holding one would have to compare a distance that does not
    exist. Dropping it here is what lets P015 fall back to `shapes.txt`.
    """
    published: dict[str, Points] = {}
    claimed: dict[str, str] = {}
    for entity in entities:
        if entity.has("shape"):
            _publish(entity.get("shape"), published, ctx)
        if entity.has("trip_update"):
            _claim_by_properties(entity.get("trip_update"), claimed)
        if entity.has("trip_modifications"):
            _claim_by_modifications(entity.get("trip_modifications"), claimed)
    return {
        trip_id: published[shape_id]
        for trip_id, shape_id in claimed.items()
        if published.get(shape_id)
    }


def _publish(found: Msg, published: dict[str, Points], ctx: RuleContext) -> None:
    """One `Shape` entity's points, swapped into `(lon, lat)`."""
    if not found.has("shape_id") or not found.has("encoded_polyline"):
        return
    decoded = polyline(found.get("encoded_polyline"), ctx)
    if decoded.error is not None:
        return
    published[found.get("shape_id")] = tuple((point[1], point[0]) for point in decoded.points)


def _claim_by_properties(update: Msg, claimed: dict[str, str]) -> None:
    """`TripUpdate.TripProperties.shape_id`, keyed by the trip it names.

    `TripProperties.trip_id` wins over the descriptor's where it is set, because
    for a NEW trip it is the id the trip is published under while the descriptor
    may still name the trip being replaced.
    """
    if not update.has("trip_properties"):
        return
    properties = update.get("trip_properties")
    if not properties.has("shape_id"):
        return
    trip = update.get("trip")
    if properties.has("trip_id"):
        claimed[properties.get("trip_id")] = properties.get("shape_id")
    elif trip.has("trip_id"):
        claimed[trip.get("trip_id")] = properties.get("shape_id")


def _claim_by_modifications(modifications: Msg, claimed: dict[str, str]) -> None:
    """`TripModifications.SelectedTrips`, which names several trips at once."""
    for selected in modifications.get("selected_trips"):
        if not selected.has("shape_id"):
            continue
        for trip_id in selected.get("trip_ids"):
            claimed[trip_id] = selected.get("shape_id")
