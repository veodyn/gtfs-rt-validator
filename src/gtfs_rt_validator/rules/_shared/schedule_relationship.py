"""Every schedule_relationship in a message, resolved once and answered by name.

Nine spec-tier rules turn on one of the two `ScheduleRelationship` enums: S004,
S007, S008, S009, S010, S013, S014, S017 and S024. All nine need the same two
things done before they can say anything, and neither is interesting enough to
do nine times. It was ten until S022 was retired for being a strict subset of
E013; `tests/writtenrules.py` carries the measurement.

**Resolving the proto2 default.** Both fields are `optional` with a default of
0, so an absent field reads `SCHEDULED` while `hasScheduleRelationship()` stays
false, and rules need both halves. A record carries `relationship` and
`declared` rather than making each rule remember which it wanted.

**Answering by name.** `TripDescriptor.ScheduleRelationship` numbers are not
contiguous (there is no 4, and `NEW` is 8), so a rule comparing numbers is a
rule whose reader has to open the .proto to check it. The names come out of the
schema, so a member renamed at a later pin fails at import here rather than
becoming a comparison that silently never matches.

**A TripDescriptor rides on three things**, and the walk reaches all three:
`TripUpdate.trip`, `VehiclePosition.trip` and `Alert.informed_entity[].trip`.
S024 is about the deprecated value wherever it appears, so a walk scoped to
TripUpdates would miss two thirds of the surface. Presence is tested before each
one: `getTrip()` on a VehiclePosition that names no trip answers a default
instance whose relationship is `SCHEDULED`, and a walk that skipped the test
would report a trip for every vehicle in the feed. `ADDED`'s deprecation comes
from `Schema.enum_deprecated`, so the fact enters the rules layer through the
pin rather than through a member name written here.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules._shared.memo import memoised
from gtfs_rt_validator.rules.errors import RuleContractError

if TYPE_CHECKING:  # Type-only: nothing under `rules/` may import the runner at
    # run time, because it reaches the static layer and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

TRIP_ENUM = "TripDescriptor.ScheduleRelationship"
STOP_TIME_ENUM = "TripUpdate.StopTimeUpdate.ScheduleRelationship"


def _member(enum: str, name: str) -> str:
    """`name`, having checked the pinned schema still declares it.

    The check is the point: a constant spelled here and nowhere else goes on
    comparing equal to nothing at all if the member is renamed, and every rule
    reading it goes quiet rather than red.
    """
    if name not in SCHEMA.enums[enum]:
        raise ValueError(f"{enum} declares no member {name} at this pin")
    return name


SCHEDULED = _member(TRIP_ENUM, "SCHEDULED")
ADDED = _member(TRIP_ENUM, "ADDED")
UNSCHEDULED = _member(TRIP_ENUM, "UNSCHEDULED")
CANCELED = _member(TRIP_ENUM, "CANCELED")
REPLACEMENT = _member(TRIP_ENUM, "REPLACEMENT")
DUPLICATED = _member(TRIP_ENUM, "DUPLICATED")
DELETED = _member(TRIP_ENUM, "DELETED")
NEW = _member(TRIP_ENUM, "NEW")

#: The stop_time_update enum's own members. `SCHEDULED` and `UNSCHEDULED` are
#: spelled twice on purpose: they are different members of different enums that
#: happen to share a name, and S007 is exactly the rule that exists because
#: upstream read one where the proto meant the other.
STOP_TIME_SCHEDULED = _member(STOP_TIME_ENUM, "SCHEDULED")
STOP_TIME_UNSCHEDULED = _member(STOP_TIME_ENUM, "UNSCHEDULED")
SKIPPED = _member(STOP_TIME_ENUM, "SKIPPED")
NO_DATA = _member(STOP_TIME_ENUM, "NO_DATA")

#: The members the pinned proto marks `[deprecated = true]`, which today is
#: `ADDED` alone. Read rather than listed, so a deprecation added at a later pin
#: reaches S024 through the regenerated schema.
DEPRECATED_TRIP_RELATIONSHIPS = SCHEMA.enum_deprecated(TRIP_ENUM)

_TRIP_NAMES = {number: name for name, number in SCHEMA.enums[TRIP_ENUM].items()}
_STOP_TIME_NAMES = {number: name for name, number in SCHEMA.enums[STOP_TIME_ENUM].items()}


def _named(names: dict[int, str], value: object, enum: str) -> str:
    name = names.get(value) if isinstance(value, int) else None
    if name is None:
        raise RuleContractError(
            f"{enum} carries no member numbered {value!r}; the decoder leaves an unrecognised "
            f"enum value absent, so this message did not come from it"
        )
    return name


def trip_relationship(trip: Any) -> str:
    """The `TripDescriptor`'s relationship by name, default resolved."""
    return _named(_TRIP_NAMES, trip.get("schedule_relationship"), TRIP_ENUM)


def stop_time_relationship(update: Any) -> str:
    """The `StopTimeUpdate`'s relationship by name, default resolved."""
    return _named(_STOP_TIME_NAMES, update.get("schedule_relationship"), STOP_TIME_ENUM)


@dataclass(frozen=True, slots=True)
class StopTimeRelationship:
    """One `stop_time_update`, resolved."""

    index: int
    update: Msg
    relationship: str
    declared: bool
    path: str


@dataclass(frozen=True, slots=True)
class TripRelationship:
    """One `TripDescriptor` in the message, and where it was found.

    `owner` is the message carrying it: a TripUpdate, a VehiclePosition or an
    EntitySelector. Rules reading `trip_properties` or `delay` want it, and the
    walk is the only thing that knew where the descriptor came from.
    """

    entity_index: int
    payload: str
    owner: Msg
    trip: Msg
    relationship: str
    declared: bool
    path: str
    stop_time_updates: tuple[StopTimeRelationship, ...] = ()


def relationships(
    message: Any, ctx: RuleContext, *, scope: str = ""
) -> tuple[TripRelationship, ...]:
    """Every `TripDescriptor` of `message`, resolved at most once per context.

    `scope` is `memo.py`'s, and S021 is why it is here: that rule resolves the
    descriptors of `ctx.previous` as well as of the message it was handed, and
    two builds over two messages in one context need two entries. Without a
    scope the second caller is handed the first message's records, silently.
    """
    return memoised(_build, message, ctx, scope=scope)


def _build(message: Any, ctx: RuleContext) -> tuple[TripRelationship, ...]:
    return tuple(
        record
        for index, entity in enumerate(message.get("entity"))
        for record in _of_entity(index, entity)
    )


def _of_entity(index: int, entity: Msg) -> Iterator[TripRelationship]:
    if entity.has("trip_update"):
        payload = entity.get("trip_update")
        path = f"entity[{index}].trip_update"
        yield _record(index, "trip_update", payload, path, tuple(_stop_times(payload, path)))
    if entity.has("vehicle"):
        payload = entity.get("vehicle")
        if payload.has("trip"):
            yield _record(index, "vehicle", payload, f"entity[{index}].vehicle")
    if entity.has("alert"):
        for position, selector in enumerate(entity.get("alert").get("informed_entity")):
            if selector.has("trip"):
                path = f"entity[{index}].alert.informed_entity[{position}]"
                yield _record(index, "alert", selector, path)


def _record(
    index: int, payload: str, owner: Msg, path: str, stops: tuple[StopTimeRelationship, ...] = ()
) -> TripRelationship:
    trip = owner.get("trip")
    return TripRelationship(
        entity_index=index,
        payload=payload,
        owner=owner,
        trip=trip,
        relationship=trip_relationship(trip),
        declared=trip.has("schedule_relationship"),
        path=f"{path}.trip",
        stop_time_updates=stops,
    )


def _stop_times(trip_update: Msg, path: str) -> Iterator[StopTimeRelationship]:
    for index, update in enumerate(trip_update.get("stop_time_update")):
        yield StopTimeRelationship(
            index=index,
            update=update,
            relationship=stop_time_relationship(update),
            declared=update.has("schedule_relationship"),
            path=f"{path}.stop_time_update[{index}]",
        )
