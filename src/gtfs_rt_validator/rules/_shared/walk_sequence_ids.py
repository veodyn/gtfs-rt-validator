"""This message's ids beside the previous one's, aligned by trip. P002 and P003.

Two rules ask the same question of two different fields. P002 asks whether the
`FeedEntity.id` carrying a trip changed between two sequential messages
(`realtime-best-practices.md:44`, "Should be kept stable over the entire trip
duration"); P003 asks the same of `VehicleDescriptor.id` (`:89`). Neither can be
answered from one message, both need exactly the same alignment, and the
alignment is the only hard part, so it happens once here and they filter it.

**"Previous" is the previous message of the same role, and this module never
decides that.** `runner/context.py` settles it: `ctx.previous` is per role, a
role whose file failed to decode is absent from its cycle rather than carried
forward, and under `--compat` there is one role so per role and global coincide.
This walk reads `ctx.previous` and nothing else, which is what keeps that
decision in one place. It also means the message handed in **must** be the one
the context was built for: handing it another role's message aligns that message
against *this* role's history, which is the exact unrelated-snapshot comparison
the contract exists to prevent. `memo.py` explains why that is a wrong answer
rather than a crash, and it is why this walk takes no `scope`: a scope would
make the wrong call expressible.

**The key is the payload and the trip together, not the trip alone.** A combined
feed carries a TripUpdate and a VehiclePosition for one trip under two different
entity ids, and `FeedEntity` ordering is specified nowhere. Keyed on `trip_id`
alone, the walk would pair a TripUpdate's entity id against a VehiclePosition's
the moment the producer emitted them in the other order, and report a stable
feed as unstable. Upstream's own `FeedMessageTest` builds one entity carrying
both payloads at once, so this is a shape the fixtures reach, not a hypothetical.

**Two entities naming one trip in one message keep the first.** That feed is
what S003 and E047 report; reporting it a third time from here would make a
stability rule fire on a defect that is not about stability. First in entity
order, so the answer does not depend on which of the two the walk happened to
see last.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gtfs_rt_validator.rules._shared.memo import memoised

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, and nothing under `rules/` may import that at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["PAYLOADS", "SequencedTrip", "TripIds", "sequence_ids"]

#: The two `FeedEntity` payloads that carry a `TripDescriptor` naming a trip in
#: service, in the order an entity carrying both is read. `alert` is not among
#: them: an `informed_entity` selects trips it is *about*, so an Alert's entity
#: id is not "the id carrying that trip" in any sense `:44` would recognise, and
#: `trip_modifications` selects trips for the same reason. Both are present in
#: the current schema and neither is in the 2015 one, so naming them here would
#: also be a schema claim this layer is not allowed to make.
PAYLOADS = ("trip_update", "vehicle")


@dataclass(frozen=True, slots=True)
class TripIds:
    """What one message says about one trip, in one payload.

    `vehicle_id` is `None` when the payload names no `VehicleDescriptor` or the
    descriptor names no `id`, and `""` when the feed set the id to the empty
    string. The two are kept apart because only the second is an id that could
    have changed: `StringUtils.isEmpty` collapses them and P003 must not.
    """

    entity_id: str
    vehicle_id: str | None
    index: int
    path: str


@dataclass(frozen=True, slots=True)
class SequencedTrip:
    """One trip's ids in this message and in the previous one, for one payload.

    Both sides are present by construction: a trip only one of the two messages
    carries is not yielded at all, because a first sighting has no earlier id to
    have moved from and a trip that has ended has no current one.
    """

    trip_id: str
    payload: str
    current: TripIds
    previous: TripIds


def sequence_ids(message: Any, ctx: RuleContext) -> tuple[SequencedTrip, ...]:
    """Every trip both this message and its role's previous one carry.

    In this message's entity order, and in `PAYLOADS` order within an entity
    that carries both. Empty for the first message of a role, which is the same
    answer as a feed whose trips are all new. Built at most once per message,
    however many rules read it.
    """
    return memoised(_build, message, ctx)


def _build(message: Any, ctx: RuleContext) -> tuple[SequencedTrip, ...]:
    if ctx.previous is None:
        return ()
    was = _ids_in(ctx.previous)
    return tuple(
        SequencedTrip(trip_id, payload, ids, was[(payload, trip_id)])
        for (payload, trip_id), ids in _ids_in(message).items()
        if (payload, trip_id) in was
    )


def _ids_in(message: Any) -> dict[tuple[str, str], TripIds]:
    """`(payload, trip_id)` to the ids carrying it, first entity winning."""
    found: dict[tuple[str, str], TripIds] = {}
    for index, entity in enumerate(message.get("entity")):
        for payload, trip_id, ids in _carried(entity, index):
            found.setdefault((payload, trip_id), ids)
    return found


def _carried(entity: Msg, index: int) -> Iterator[tuple[str, str, TripIds]]:
    """Each payload of one entity that names a trip, with the ids it carries."""
    entity_id = entity.get("id")
    for payload in PAYLOADS:
        if not entity.has(payload):
            continue
        carrier = entity.get(payload)
        trip = carrier.get("trip")
        if not carrier.has("trip") or not trip.has("trip_id"):
            continue
        path = f"entity[{index}].{payload}"
        yield payload, trip.get("trip_id"), TripIds(entity_id, _vehicle_id(carrier), index, path)


def _vehicle_id(carrier: Msg) -> str | None:
    """`hasVehicle() && getVehicle().hasId() ? getVehicle().getId() : null`.

    The same shape `_shared/crossfeed.py:_nested` uses, and for the same reason:
    absent and blank are different feeds and a rule about identity has to see
    which one it was handed.
    """
    if not carrier.has("vehicle"):
        return None
    vehicle = carrier.get("vehicle")
    return vehicle.get("id") if vehicle.has("id") else None
