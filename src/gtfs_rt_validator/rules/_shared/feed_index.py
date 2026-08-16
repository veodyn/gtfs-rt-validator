"""What one message defines, indexed once. The spec tier's cross-reference table.

Seven rules resolve an id against the feed itself rather than against the static
feed: S016 and S044 look for a `shape_id`, S043, S046 and S047 for a `stop_id`,
S045 for a trip already replaced, S020 for a `TripProperties.trip_id`. All seven
ask "does this message define that", and this is the one place that answers.

**It is built from the whole message, and that is a correctness property rather
than an optimisation.** `FeedEntity` ordering is not specified anywhere in the
proto, so a `TripModifications` entity may precede the `Shape` entity it names.
An index filled in as a walk went would resolve the reference in one order and
report a correct feed as broken in the other, and the fixture that caught it
would have to be the one with the unlucky order. Reversing the entities is what
`tests/test_shared_feed_index.py` asserts instead.

**An entity that defines no id is not indexed.** `Shape.shape_id` and
`Stop.stop_id` are both `optional`, which is S037's and S042's neighbourhood;
indexing one under the empty string would make every other rule's lookup of an
empty id succeed, which is the worst possible answer to give a rule whose whole
job is to say an id does not resolve.

**Two entities claiming one id keep the first.** No rule in either cited tier
reports a feed that defines one `shape_id` twice, and the seven readers ask only
whether the id is defined, so the choice reaches nothing. It is written down
because it is the one thing here that is not order-independent, and a rule that
came to depend on *which* entity it got would need the index to keep both.

**A second message in one context needs a scope.** S020 reads a VehiclePosition
against the TripUpdates of the same cycle, which is a message this context was
not built for. `memo.py` says why: `index(other, ctx, scope=role)` is a second
entry, and `index(other, ctx)` is this message's index with somebody else's
question asked of it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.rules._shared.memo import memoised
from gtfs_rt_validator.rules._shared.schedule_relationship import REPLACEMENT, trip_relationship

if TYPE_CHECKING:  # Type-only: nothing under `rules/` may import the runner at
    # run time, because it reaches the static layer and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["FeedIndex", "index"]


@dataclass(frozen=True, slots=True)
class FeedIndex:
    """Everything one `FeedMessage` defines that another entity may reference."""

    #: Every `FeedEntity.id`. S016 and S044 report the specific mistake `:414`
    #: and `:1201` warn against, writing the entity id where the `shape_id`
    #: inside the entity was meant, and this is how they recognise it.
    entity_ids: frozenset[str]

    #: `Shape.shape_id` to the `Shape` that declared it.
    shapes: Mapping[str, Msg]

    #: `Stop.stop_id` to the `Stop` that declared it. A `Stop` entity has no
    #: `location_type` field at this pin, so S047 reads location_type from
    #: `stops.txt` and treats a stop defined here as routable.
    stops: Mapping[str, Msg]

    #: `TripUpdate.TripProperties.trip_id`, which S020 pairs a DUPLICATED
    #: VehiclePosition's `trip_id` against. A different field from the
    #: descriptor's own trip_id, which is why S020 is not E047.
    trip_property_trip_ids: frozenset[str]

    #: `TripDescriptor.trip_id` to the TripUpdate that declares it REPLACEMENT.
    #: S045 fires when a selected trip already has one.
    replacement_trip_updates: Mapping[str, Msg]

    def defines_shape(self, shape_id: str) -> bool:
        return shape_id in self.shapes

    def defines_stop(self, stop_id: str) -> bool:
        return stop_id in self.stops


def index(message: Any, ctx: RuleContext, *, scope: str = "") -> FeedIndex:
    """What `message` defines, built at most once per context and scope."""
    return memoised(_build, message, ctx, scope=scope)


def _build(message: Any, ctx: RuleContext) -> FeedIndex:
    entity_ids: set[str] = set()
    shapes: dict[str, Msg] = {}
    stops: dict[str, Msg] = {}
    trip_property_trip_ids: set[str] = set()
    replacements: dict[str, Msg] = {}
    for entity in message.get("entity"):
        entity_ids.add(entity.get("id"))
        if entity.has("shape"):
            _claim(shapes, entity.get("shape"), "shape_id")
        if entity.has("stop"):
            _claim(stops, entity.get("stop"), "stop_id")
        if entity.has("trip_update"):
            _read_trip_update(entity.get("trip_update"), trip_property_trip_ids, replacements)
    return FeedIndex(
        entity_ids=frozenset(entity_ids),
        shapes=shapes,
        stops=stops,
        trip_property_trip_ids=frozenset(trip_property_trip_ids),
        replacement_trip_updates=replacements,
    )


def _claim(into: dict[str, Msg], defined: Msg, field: str) -> None:
    """Index `defined` under its own id, unless it declares none."""
    if defined.has(field):
        into.setdefault(defined.get(field), defined)


def _read_trip_update(
    trip_update: Msg, trip_property_trip_ids: set[str], replacements: dict[str, Msg]
) -> None:
    properties = trip_update.get("trip_properties")
    if properties.has("trip_id"):
        trip_property_trip_ids.add(properties.get("trip_id"))
    trip = trip_update.get("trip")
    if trip.has("trip_id") and trip_relationship(trip) == REPLACEMENT:
        replacements.setdefault(trip.get("trip_id"), trip_update)
