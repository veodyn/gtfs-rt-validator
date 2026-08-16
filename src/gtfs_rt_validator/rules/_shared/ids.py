"""The identifier text that prefixes an occurrence, ported from `GtfsUtils`.

Seven helpers out of `util/GtfsUtils.java`, every one of which builds a string
that ends up inside an occurrence's `prefix` and therefore inside the bytes the
differential compares. There is no room here for a tidier phrasing: the text is
the contract.

Four details are load-bearing and each one looks like a typo until you read
the Java.

- `vehicle.id` has a **dot**, not an underscore, in `vehicle_id_text` and
  `vehicle_descriptor_id_text` (GtfsUtils.java:226). Every rule title spells the
  field `vehicle_id`, and this one place spells it `vehicle.id`.
- `stop_time_update_id_text` renders the stop_sequence **signed**, through
  `javafmt.int32_str`. protobuf-java maps `uint32` onto Java's `int`, so a
  stop_sequence above 2^31-1 prints as a negative. This helper only prints; the
  walks that also compare the field narrow it at the read, which is the same
  conversion applied one step earlier.
- `stop_time_update_id_text` falls back to `stop_id` **unguarded**
  (GtfsUtils.java:240). A stop_time_update carrying neither a stop_sequence nor
  a stop_id yields `"stop_id "`, trailing space included.
- `vehicle_and_trip_id_text` and `vehicle_and_route_id_text` chain through
  `getVehicle()` and `getTrip()` with no presence check at all
  (GtfsUtils.java:101 and :122), so absent fields interpolate as the empty
  string. These two never fall back to the entity ID, unlike the five above
  them; a VehiclePosition with nothing set gives `"vehicle_id  trip_id "`,
  double space and all.

Java resolves `getTripId` and `getVehicleId` by the static type of the second
argument. Python has one `Msg` for every message, so the two overloads of each
are two named functions rather than one dispatching on `desc.name`: a caller
that passes the wrong kind then fails at the call it wrote instead of quietly
taking the other branch.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.rules._shared.javafmt import int32_str
from gtfs_rt_validator.rules.errors import RuleContractError

_VEHICLE_AND = ("VehiclePosition", "TripUpdate")


def trip_id_text(entity: Msg, trip_update: Msg) -> str:
    """`getTripId(FeedEntity, TripUpdate)`, GtfsUtils.java:183-188.

    The `!hasTrip()` shortcut is unreachable through the decoder, since
    `TripUpdate.trip` is required at both pins and a TripUpdate without one
    fails `isInitialized` before any rule runs. It is ported anyway: it is one
    line, and a helper that matches the Java line for line is a helper nobody
    has to re-derive.
    """
    if not trip_update.has("trip"):
        return "entity ID " + entity.get("id")
    return trip_descriptor_id_text(entity, trip_update.get("trip"))


def trip_descriptor_id_text(entity: Msg, trip: Msg) -> str:
    """`getTripId(FeedEntity, TripDescriptor)`, GtfsUtils.java:198-200."""
    if trip.has("trip_id"):
        return "trip_id " + trip.get("trip_id")
    return "entity ID " + entity.get("id")


def vehicle_id_text(entity: Msg, vehicle_position: Msg) -> str:
    """`getVehicleId(FeedEntity, VehiclePosition)`, GtfsUtils.java:210-215."""
    if not vehicle_position.has("vehicle"):
        return "entity ID " + entity.get("id")
    return vehicle_descriptor_id_text(entity, vehicle_position.get("vehicle"))


def vehicle_descriptor_id_text(entity: Msg, vehicle: Msg) -> str:
    """`getVehicleId(FeedEntity, VehicleDescriptor)`, GtfsUtils.java:225-227.

    `vehicle.id`, with the dot. See the module docstring.
    """
    if vehicle.has("id"):
        return "vehicle.id " + vehicle.get("id")
    return "entity ID " + entity.get("id")


def stop_time_update_id_text(stop_time_update: Msg) -> str:
    """`getStopTimeUpdateId(StopTimeUpdate)`, GtfsUtils.java:236-242.

    stop_sequence wins when present, even alongside a stop_id. The `else` arm
    reads `getStopId()` with no `hasStopId()` guard, so an update carrying
    neither gives `"stop_id "` and a trailing space.

    `int32_str` rather than `str`: `getStopSequence()` returns a Java `int`, so
    a `uint32` past 2^31-1 concatenates as a negative. Measured on the jar,
    `stop_sequence = 4294967295` gives `"stop_sequence -1"` here and in the four
    other places this field is printed. E042, E043, E044, E046 and W009 all
    reach this one line, which is why the conversion is here rather than in each
    of them.
    """
    if stop_time_update.has("stop_sequence"):
        return "stop_sequence " + int32_str(stop_time_update.get("stop_sequence"))
    return "stop_id " + stop_time_update.get("stop_id")


def vehicle_and_trip_id_text(entity: Msg) -> str:
    """`getVehicleAndTripIdText(Object)`, GtfsUtils.java:94-107.

    `entity` keeps the Java parameter's name, though what it takes is the
    VehiclePosition or TripUpdate itself rather than the FeedEntity around it.
    """
    _require_vehicle_or_trip(entity)
    if entity.desc.name == "VehiclePosition":
        vehicle = entity.get("vehicle")
        trip = entity.get("trip")
        return "vehicle_id " + vehicle.get("id") + " trip_id " + trip.get("trip_id")
    return "trip_id " + entity.get("trip").get("trip_id")


def vehicle_and_route_id_text(entity: Msg) -> str:
    """`getVehicleAndRouteId(Object)`, GtfsUtils.java:115-128."""
    _require_vehicle_or_trip(entity)
    if entity.desc.name == "VehiclePosition":
        vehicle = entity.get("vehicle")
        trip = entity.get("trip")
        return "vehicle_id " + vehicle.get("id") + " route_id " + trip.get("route_id")
    return "route_id " + entity.get("trip").get("route_id")


def _require_vehicle_or_trip(entity: Msg) -> None:
    """Java throws `IllegalArgumentException` here, and this is its port.

    `RuleContractError` rather than a new type or a bare `TypeError`. The
    project's line is that notices are data and exceptions are bugs in this
    repository, and that is exactly what this is: not a malformed feed, but a
    rule module handing a shared helper a message kind the helper does not
    serve. `RuleContractError` is already the name for "a module here got the
    contract wrong, so raise rather than record", it is caught nowhere, and a
    second exception meaning the same thing would only split the concept.
    """
    if entity.desc.name not in _VEHICLE_AND:
        raise RuleContractError(
            f"expected a VehiclePosition or a TripUpdate, got a {entity.desc.name}"
        )
