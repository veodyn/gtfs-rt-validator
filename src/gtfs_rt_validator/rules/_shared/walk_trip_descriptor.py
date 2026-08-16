"""`TripDescriptorValidator`'s one pass over the entities, as a shared walk.

`validation/rules/TripDescriptorValidator.java:94-199` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. Fifteen reported ids come out of
this loop, and each has a module of its own that filters the stream with
`walks.events_for`. The bodies of the checks are in
`trip_descriptor_checks.py` and `trip_descriptor_alert_checks.py`; what is here
is upstream's control flow, which is the part no rule can reconstruct alone.

**Three independent halves per entity**, in this order: TripUpdate (`:95-141`),
VehiclePosition (`:142-176`, gated on `hasVehicle() && getVehicle().hasTrip()`)
and Alert (`:177-198`). An entity carrying all three is examined three times,
which is how upstream's own `testE035` reaches three occurrences of one rule
from one entity.

**The two vehicle-bearing halves are not symmetric**, and the asymmetry is
deliberate enough to be worth naming twice:

- The VehiclePosition side tests `StringUtils.isEmpty(tripId)` at `:148` before
  looking the trip up. The TripUpdate side has no such test, so a trip_id set to
  the empty string is looked up there and reported as E003, and skipped here.
- The four unconditional checks run `E021, E004, E024, E035` on the TripUpdate
  side (`:122-125`) and `E004, E021, E024, E035` on the VehiclePosition side
  (`:171-174`). Upstream writes each to its own list, so there the order reaches
  no output byte; here they share one stream, so it is reproduced. What the
  reversal actually swaps is a call to `getVehicleAndRouteId` (E004, `:262`)
  against one to `getVehicleAndTripIdText` (E021, `:316`): two different
  helpers, not two overloads of one.

**`checkE035` is called unconditionally in the alert half** (`:184`), outside
the `hasTrip()` guard that wraps W006 and W009, so a selector with no trip hands
it the default TripDescriptor and `hasTripId()` short-circuits.

**W009's suppression list is whole-feed, and that is a bug to reproduce.**
`errorListW009` is created once per `validate` call and never reset per entity,
so `w009` below is a list rather than a counter and is read exactly where
upstream reads `!errorListW009.isEmpty()`. Once any W009 exists anywhere in the
feed, including one produced by an earlier entity's TripDescriptor, the *first*
stop_time_update of every later TripUpdate sets `found_w009` whether or not it
added anything, and that trip's remaining stop_time_updates are never checked. A
port with a per-trip list emits strictly more occurrences than the jar. See
`tests/test_rule_w009.py`.

The entity path on each event is this project's, not upstream's: `--compat`
writes the prefix alone, and a modern report needs to say which selector or
which stop_time_update a finding came from.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.ids import trip_id_text
from gtfs_rt_validator.rules._shared.trip_descriptor_alert_checks import (
    check_e030,
    check_e031,
    check_e033,
    check_e034,
)
from gtfs_rt_validator.rules._shared.trip_descriptor_checks import (
    Found,
    check_e004,
    check_e020,
    check_e021,
    check_e023,
    check_e024,
    check_e035,
    check_w006,
    check_w009_stop_time_update,
    check_w009_trip,
    is_added_trip,
)
from gtfs_rt_validator.rules._shared.walks import Event

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["trip_descriptors"]


def _events(path: str, *findings: Found) -> Iterator[Event]:
    """The findings that were findings, at the position the loop was standing.

    Variadic so a run of `checkXxx` calls reads as the run of them the Java is.
    Every argument is evaluated before this is entered, which costs nothing:
    every check is a pure function of the message and the static feed.
    """
    for found in findings:
        if found is not None:
            yield Event(found[0], found[1], {ENTITY_PATH_KEY: path})


def _w009(recorded: list[Event], found: Found, path: str) -> Iterator[Event]:
    """A W009, both yielded and appended to the list upstream never resets."""
    for event in _events(path, found):
        recorded.append(event)
        yield event


def _trip_update(entity: Msg, index: int, ctx: RuleContext, w009: list[Event]) -> Iterator[Event]:
    """`:95-141`. The half that owns both W009 overloads."""
    trip_update = entity.get("trip_update")
    trip = trip_update.get("trip")
    path = f"entity[{index}].trip_update.trip"
    if not trip.has("trip_id"):
        yield from _events(path, check_w006(entity, trip))
    else:
        gtfs_trip = ctx.static.trips.get(trip.get("trip_id"))
        if gtfs_trip is None:
            if not is_added_trip(trip):
                yield from _events(path, ("E003", trip_id_text(entity, trip_update)))
        else:
            if is_added_trip(trip):
                yield from _events(path, ("E016", trip_id_text(entity, trip_update)))
            if trip.has("start_time"):
                yield from _events(path, check_e023(trip_update, trip, ctx))

    if trip.has("start_time"):
        yield from _events(path, check_e020(trip_update, trip))
    yield from _events(
        path,
        check_e021(trip_update, trip),
        check_e004(trip_update, trip, ctx),
        check_e024(trip_update, trip, ctx),
        check_e035(entity, trip, ctx),
    )

    found_w009 = False
    for position, stop_time_update in enumerate(trip_update.get("stop_time_update")):
        # `:130-131`, upstream's own comment: "Only flag one occurrence of W009
        # for stop_time_update per trip to avoid flooding the database". The
        # list it consults to decide that is the feed's, not the trip's.
        if not found_w009:
            at = f"entity[{index}].trip_update.stop_time_update[{position}]"
            yield from _w009(w009, check_w009_stop_time_update(entity, stop_time_update), at)
            if w009:
                found_w009 = True
    if trip_update.has("trip"):
        yield from _w009(w009, check_w009_trip(entity, trip), path)


def _vehicle(entity: Msg, index: int, ctx: RuleContext, w009: list[Event]) -> Iterator[Event]:
    """`:142-176`, entered only when the VehiclePosition has a trip.

    E003 and E016 build their prefix inline here (`:153` and `:158`) rather than
    through `getVehicleAndTripIdText`, and the two texts differ: this one reads
    `getVehicle().getVehicle().getId()` with no presence check and pastes the
    trip_id local after it.
    """
    position = entity.get("vehicle")
    trip = position.get("trip")
    path = f"entity[{index}].vehicle.trip"
    if not trip.has("trip_id"):
        yield from _events(path, check_w006(entity, trip))
    elif trip.get("trip_id") != "":
        trip_id = trip.get("trip_id")
        named = f"vehicle_id {position.get('vehicle').get('id')} trip_id {trip_id}"
        gtfs_trip = ctx.static.trips.get(trip_id)
        if gtfs_trip is None:
            if not is_added_trip(trip):
                yield from _events(path, ("E003", named))
        else:
            if is_added_trip(trip):
                yield from _events(path, ("E016", named))
            if trip.has("start_time"):
                yield from _events(path, check_e023(position, trip, ctx))

    if trip.has("start_time"):
        yield from _events(path, check_e020(position, trip))
    yield from _events(
        path,
        check_e004(position, trip, ctx),
        check_e021(position, trip),
        check_e024(position, trip, ctx),
        check_e035(entity, trip, ctx),
    )
    yield from _w009(w009, check_w009_trip(entity, trip), path)


def _alert(entity: Msg, index: int, ctx: RuleContext, w009: list[Event]) -> Iterator[Event]:
    """`:177-198`. Every check here is per informed_entity except E032."""
    selectors = entity.get("alert").get("informed_entity")
    if not selectors:
        text = f"alert ID {entity.get('id')} does not have an informed_entity"
        yield from _events(f"entity[{index}].alert", ("E032", text))
        return
    for position, selector in enumerate(selectors):
        path = f"entity[{index}].alert.informed_entity[{position}]"
        yield from _events(
            path,
            check_e033(entity, selector),
            check_e034(entity, selector, ctx),
            check_e035(entity, selector.get("trip"), ctx),
        )
        if selector.has("route_id") and selector.has("trip"):
            yield from _events(
                path, check_e030(entity, selector, ctx), check_e031(entity, selector)
            )
        if selector.has("trip"):
            trip = selector.get("trip")
            yield from _events(path, check_w006(entity, trip))
            yield from _w009(w009, check_w009_trip(entity, trip), path)


def trip_descriptors(message: Msg, ctx: RuleContext) -> Iterator[Event]:
    """One pass over the entities, three independent halves each.

    `w009` is `errorListW009`: one list for the whole feed, handed to every
    half, never reset. It is the walk's only state, and reproducing its lifetime
    is most of the reason this loop is shared rather than repeated.
    """
    w009: list[Event] = []
    for index, entity in enumerate(message.get("entity")):
        if entity.has("trip_update"):
            yield from _trip_update(entity, index, ctx, w009)
        if entity.has("vehicle") and entity.get("vehicle").has("trip"):
            yield from _vehicle(entity, index, ctx, w009)
        if entity.has("alert"):
            yield from _alert(entity, index, ctx, w009)
