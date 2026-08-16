"""The two things cohort D's `TripDescriptor` rules share, and why not `ids.py`.

`rules/_shared/ids.py` already renders a descriptor into occurrence text, and no
rule here may use it. That module is a port of `util/GtfsUtils.java` whose output
is compared against the jar byte for byte, and every helper in it falls back to
`"entity ID " + entity.getId()` when the descriptor names no trip. The spec-tier
rules below are handed the descriptor by `_shared/schedule_relationship.py`,
which knows the entity's index and not its id, and they have no jar to match. So
they say what they mean in their own words, and this is where those words live
once rather than in five modules.

**`route_scoped` is the antecedent S018 and S019 both test**, and it is the
second bullet of the `TripDescriptor` message comment at `:797`: "To specify all
the trips along a given route, only the route_id should be set." A descriptor
carrying a route_id and no trip_id is a prediction about every trip on a route,
which is the shape both clauses then constrain. Presence, not emptiness: that is
how `_shared/trip_descriptor_checks.py` reads the same two fields for W006 and
E035, and a spec rule disagreeing with the compat tier about what "set" means
would be a difference nobody chose.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.decode import Msg

__all__ = ["route_scoped", "route_text", "trip_text"]


def route_scoped(trip: Msg) -> bool:
    """Whether this descriptor names a route and no trip. S018's and S019's if."""
    return trip.has("route_id") and not trip.has("trip_id")


def route_text(trip: Msg) -> str:
    """How S018 and S019 open an occurrence, the route being all there is."""
    return "route_id " + trip.get("route_id")


def trip_text(trip: Msg) -> str:
    """How S021, S023 and S024 name the trip an occurrence is about.

    A descriptor with no trip_id is named as such rather than falling back to an
    entity id, which these rules are not handed. The fallback text is a sentence
    rather than an id because the occurrence's `entityPath` already says where
    it was, and repeating the index in the prefix would say it twice.
    """
    return "trip_id " + trip.get("trip_id") if trip.has("trip_id") else "a trip with no trip_id"
