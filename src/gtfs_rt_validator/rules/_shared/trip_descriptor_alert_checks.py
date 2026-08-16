"""The four `TripDescriptorValidator` checks only an alert reaches.

E030 (`:350-361`), E031 (`:371-378`), E033 (`:388-405`) and E034 (`:416-422`)
each take a `FeedEntity` and one of its `informed_entity` selectors, and no
other half of the dispatch calls any of them. Split out of
`trip_descriptor_checks.py` at the file-size cap; the seam is upstream's own
parameter list rather than an invention.

E032 has no `checkE032` to port: it is a bare `addOccurrence` in the `else` of
the informed_entity test, so its text lives in the dispatch beside the branch
that decides it.

The same `Found` contract as the sibling module: `(rule_id, prefix)` or `None`,
with the entity path attached by the dispatch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.rules._shared.trip_descriptor_checks import Found

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["check_e030", "check_e031", "check_e033", "check_e034"]


def check_e030(entity: Msg, entity_selector: Msg, ctx: RuleContext) -> Found:
    """`checkE030`, `:350-361`. `routeId` is the *selector's*, not the trip's.

    Called only when the selector has both a route_id and a trip (`:185`), and
    then guarded again on `hasTripId()` inside. A trip_id absent from
    `trips.txt` is E003's finding, not this one's.
    """
    route_id = entity_selector.get("route_id")
    trip = entity_selector.get("trip")
    if not trip.has("trip_id"):
        return None
    trip_id = trip.get("trip_id")
    gtfs_trip = ctx.static.trips.get(trip_id)
    if gtfs_trip is None:
        return None
    gtfs_route_id = gtfs_trip["route_id"]
    if route_id == gtfs_route_id:
        return None
    return (
        "E030",
        (
            f"alert ID {entity.get('id')} informed_entity.trip.trip_id {trip_id} "
            f"does not belong to informed_entity.route_id {route_id} "
            f"(GTFS says it belongs to route_id {gtfs_route_id})"
        ),
    )


def check_e031(entity: Msg, entity_selector: Msg) -> Found:
    """`checkE031`, `:371-378`. Reads no static data at all.

    Shares E030's gate at `:185`, so a selector with a trip but no route_id
    reaches neither, however different the two comparisons are.
    """
    trip = entity_selector.get("trip")
    if not trip.has("route_id"):
        return None
    route_id = entity_selector.get("route_id")
    trip_route_id = trip.get("route_id")
    if trip_route_id == route_id:
        return None
    return (
        "E031",
        (
            f"alert ID {entity.get('id')} informed_entity.route_id {route_id} "
            f"does not equal informed_entity.trip.route_id {trip_route_id}"
        ),
    )


def check_e033(entity: Msg, entity_selector: Msg) -> Found:
    """`checkE033`, `:388-405`. A selector carrying only an empty trip fires.

    The trip is read into a local that stays null unless `hasTrip()`, so the
    inner test is "no trip at all, or a trip with neither a trip_id nor a
    route_id". A route_type or a stop_id on the selector settles it before the
    trip is consulted.

    The doubled "not not" at `:402` is upstream's and is reproduced verbatim.
    """
    if (
        entity_selector.has("agency_id")
        or entity_selector.has("route_id")
        or entity_selector.has("route_type")
        or entity_selector.has("stop_id")
    ):
        return None
    trip = entity_selector.get("trip") if entity_selector.has("trip") else None
    if trip is not None and (trip.has("trip_id") or trip.has("route_id")):
        return None
    return (
        "E033",
        (
            f"alert ID {entity.get('id')} informed_entity and informed_entity.trip "
            "do not not reference any agency, route, trip, or stop"
        ),
    )


def check_e034(entity: Msg, entity_selector: Msg, ctx: RuleContext) -> Found:
    """`checkE034`, `:416-422`.

    `agency_ids` holds agency *names* for a feed whose `agency_id` column is
    blank, because `BatchProcessor` never calls `setDefaultAgencyId`. That is
    reproduced in `static/_tables.py`, not here.
    """
    if not entity_selector.has("agency_id"):
        return None
    agency_id = entity_selector.get("agency_id")
    if agency_id in ctx.static.agency_ids:
        return None
    return ("E034", f"alert ID {entity.get('id')} agency_id {agency_id}")
