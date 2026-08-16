"""`VehicleValidator`'s one pass over the entities, read by its seven rules.

Ported from `validation/rules/VehicleValidator.java:60-129` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. The walk contract, the memo and
`Event` live in `walks.py`; this is one walk, kept out of that module because it
is the contract every other walk shares and several are being written at once.
The two geometry checks and the alert scan are in `vehicle_bounds.py`.

**The nesting is the point.** Four rules share `:106-127`, and three of the four
cannot state their own condition: E028 runs only for a position that is present,
complete and inside the world, and E029 only when E028 said the vehicle was
inside the agency's box. A port that evaluated E029's own condition
independently would report every vehicle outside the agency area a second time,
against a trip shape hundreds of miles away, which the jar never does. E027 is a
sibling of the E026 if/else rather than a branch of it, so an invalid position
and an invalid bearing are both reported.

W002 and E052 sit above that block. W002 has one site in the TripUpdate half and
one in the VehiclePosition half, and E052 is the `else` of the second, so a
blank vehicle.id is a warning and is never a duplicate.

Events come out in the Java's own execution order, which is **not** the order
its seven output groups are written in (`:131-152`: E026, E027, E028, E029,
W002, W004, E052). Group order belongs to the writer. Within a group the order
is entity order, which is what this preserves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.ids import trip_id_text, vehicle_id_text
from gtfs_rt_validator.rules._shared.javafmt import float32_str, fmt2
from gtfs_rt_validator.rules._shared.positions import (
    is_bearing_valid,
    is_position_valid,
    is_position_within_shape,
    to_miles_per_hour,
)
from gtfs_rt_validator.rules._shared.vehicle_bounds import (
    e028_prefix,
    e029_prefix,
    has_detour_alert,
    inside_agency_bounds,
    position_text,
)
from gtfs_rt_validator.rules._shared.walks import Event

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, and nothing under `rules/` may import that at run time.
    # `tests/test_only_adapter_touches_the_sibling.py` is the check.
    from collections.abc import Iterator, Sequence

    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["MAX_REALISTIC_SPEED_METERS_PER_SECOND", "vehicles"]

#: `VehicleValidator.java:57`, declared `26.0f`. Exactly representable, so the
#: float32 narrowing Java applies to the comparison is a no-op here.
MAX_REALISTIC_SPEED_METERS_PER_SECOND = 26.0


def vehicles(message: Any, ctx: RuleContext) -> Iterator[Event]:
    """Every event `VehicleValidator` logs for this message, in its own order."""
    entities = message.get("entity")
    seen_vehicle_ids: set[str] = set()
    for index, entity in enumerate(entities):
        if entity.has("trip_update"):
            yield from _trip_update_half(entity, f"entity[{index}].trip_update")
        if entity.has("vehicle"):
            yield from _vehicle_half(
                entities, entity, seen_vehicle_ids, ctx, f"entity[{index}].vehicle"
            )


def _at(path: str) -> dict[str, object]:
    """A fresh context per event: `Event` is frozen, the dict inside it is not."""
    return {ENTITY_PATH_KEY: path}


def _trip_update_half(entity: Msg, path: str) -> Iterator[Event]:
    """`:73-80`. One site, with no `hasVehicle()` guard on it.

    `getVehicle()` on a TripUpdate carrying no VehicleDescriptor answers the
    default instance, whose `getId()` is `""`, which `StringUtils.isEmpty` calls
    empty. So a TripUpdate that names no vehicle at all is a W002, which is the
    whole point of the rule.
    """
    trip_update = entity.get("trip_update")
    if not trip_update.get("vehicle").get("id"):
        yield Event("W002", trip_id_text(entity, trip_update), _at(path))


def _vehicle_half(
    entities: Sequence[Msg], entity: Msg, seen: set[str], ctx: RuleContext, path: str
) -> Iterator[Event]:
    """`:81-128`, in order: W002 or E052, then W004, then the position block."""
    vehicle_position = entity.get("vehicle")
    vehicle_id = vehicle_position.get("vehicle").get("id")
    if not vehicle_id:
        yield Event("W002", "entity ID " + entity.get("id"), _at(path))
    elif vehicle_id in seen:
        prefix = "entity ID " + entity.get("id") + " has vehicle.id " + vehicle_id
        yield Event("E052", prefix, _at(path))
    else:
        seen.add(vehicle_id)

    if not vehicle_position.has("position"):
        return
    yield from _check_speed(entity, vehicle_position, path)
    yield from _check_position(entities, entity, vehicle_position, ctx, path)


def _check_speed(entity: Msg, vehicle_position: Msg, path: str) -> Iterator[Event]:
    """W004, `:96-104`. Both bounds are strict, so exactly 26.0 and 0.0 pass.

    The mph figure is `String.format("%.2f", ...)` with no `Locale`, so its
    decimal separator follows the JVM default; see `vehicle_bounds.py`.
    """
    position = vehicle_position.get("position")
    if not position.has("speed"):
        return
    speed = position.get("speed")
    if speed > MAX_REALISTIC_SPEED_METERS_PER_SECOND or speed < 0.0:
        prefix = (
            vehicle_id_text(entity, vehicle_position)
            + " speed of "
            + float32_str(speed)
            + " m/s ("
            + fmt2(to_miles_per_hour(speed))
            + " mph)"
        )
        yield Event("W004", prefix, _at(path))


def _check_position(
    entities: Sequence[Msg], entity: Msg, vehicle_position: Msg, ctx: RuleContext, path: str
) -> Iterator[Event]:
    """`:106-127`, the shared nest. See the module docstring."""
    position = vehicle_position.get("position")
    id_text = vehicle_id_text(entity, vehicle_position)
    if not position.has("latitude") or not position.has("longitude"):
        # Unreachable through a decode: `Position.latitude` and `.longitude` are
        # `required` under both schemas, so protobuf-java and `proto/decode.py`
        # alike refuse the message before any rule sees it. Ported because the
        # Java tests it first; `tests/test_rule_e026.py` pins both facts.
        yield Event("E026", id_text + " position is missing lat/long", _at(path))
    elif not is_position_valid(position):
        prefix = id_text + " has latitude/longitude of " + position_text(position)
        yield Event("E026", prefix, _at(path))
    else:
        inside, description = inside_agency_bounds(position, ctx)
        if not inside:
            yield Event("E028", e028_prefix(entity, vehicle_position, description), _at(path))
        else:
            yield from _check_trip_shape(entities, entity, vehicle_position, ctx, path)

    if not is_bearing_valid(position):
        bearing = float32_str(position.get("bearing"))
        yield Event("E027", id_text + " has bearing of " + bearing, _at(path))


def _check_trip_shape(
    entities: Sequence[Msg], entity: Msg, vehicle_position: Msg, ctx: RuleContext, path: str
) -> Iterator[Event]:
    """`checkE029`, `:200-232`, reached only when E028 said inside.

    Three early returns before anything is measured: no trip_id on the vehicle,
    no buffered shape for that trip, and a DETOUR alert covering it. The middle
    one is why `-ignoreShapes` disables this rule without saying so, since it
    leaves every trip shape null.
    """
    trip = vehicle_position.get("trip")
    if not vehicle_position.has("trip") or not trip.has("trip_id"):
        return
    trip_id = trip.get("trip_id")
    route_id = trip.get("route_id") if trip.has("route_id") else None
    shape = ctx.static.buffered_trip_shape(trip_id)
    if shape is None:
        return
    if is_position_within_shape(vehicle_position.get("position"), shape):
        return
    if has_detour_alert(entities, trip_id, route_id):
        return
    yield Event("E029", e029_prefix(entity, vehicle_position, trip_id), _at(path))
