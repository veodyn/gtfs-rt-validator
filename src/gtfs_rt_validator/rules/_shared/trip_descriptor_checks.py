"""`TripDescriptorValidator`'s checks, minus the four only an alert reaches.

Split off `walk_trip_descriptor.py` along the seam upstream already has: that
module keeps the dispatch (`:94-199`), which decides *which* check runs, *how
often* and *in what order*, and this one keeps each `checkXxx` body, which
decides what it found and what it writes. The four the alert half alone calls
are in `trip_descriptor_alert_checks.py`, which is the file-size cap's split
rather than upstream's. Three of the fifteen ids have no body in either: E003
and E016 are inlined into the dispatch, and E032 is a bare `addOccurrence` in
the `else` of the informed_entity test.

**A check returns a `Found`, not an `Event`.** Upstream's checks take the error
list and append to it; ours hand back `(rule_id, prefix)` or `None`, and the
dispatch attaches the entity path, because the path is a fact about where the
loop was standing rather than about what the check decided. See
`_shared/walks.Event`.

**Java's two parameter kinds are kept apart.** The methods that build vehicle
text take an `Object entity` that is the TripUpdate or the VehiclePosition
itself (`:259`, `:273`, `:287`, `:313`, `:329`); the rest take the `FeedEntity`.
The parameters below are named `carrier` and `entity` to keep that distinction
visible, since Python has one `Msg` for both and mixing them would silently
produce the other helper's text.

Two static-layer values do not arrive as onebusaway would deliver them, and both
are converted here rather than anywhere else:

- **`arrival_time`.** onebusaway's `StopTime.getArrivalTime()` is a primitive
  `int` whose unset value is the `MISSING_VALUE` sentinel -999; the sibling
  loader gives `None`. E023 formats that number into occurrence text, so the
  sentinel has to be restored before `seconds_after_midnight_to_clock` sees it.
- **`direction_id`.** onebusaway's `Trip.getDirectionId()` is a `String` holding
  the raw cell and the comparison is `String.equals(String.valueOf(int))`; the
  sibling types the column as an enum and hands back an `int` or `None`. The
  `None` half is reproduced exactly, including the literal "null" in the text.
  The raw-string half is not reachable from here, and the sibling cannot make it
  reachable: it stores an ENUM column as an integer and discards the cell. So
  "00", "000", "+0", "-0" and "01" all arrive as the int the realtime side
  carries and match, where the jar compares the raw cell and reports. Measured,
  one jar run per cell, and pinned as a strict xfail in `tests/test_rule_e024.py`.
  Whitespace is not in that set: onebusaway trims, so the two agree on " 0".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.rules._shared.ids import (
    stop_time_update_id_text,
    trip_descriptor_id_text,
    vehicle_and_route_id_text,
    vehicle_and_trip_id_text,
)
from gtfs_rt_validator.rules._shared.javafmt import int32
from gtfs_rt_validator.rules._shared.timeformats import is_valid_date_format, is_valid_time_format
from gtfs_rt_validator.rules._shared.times import seconds_after_midnight_to_clock

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = [
    "ADDED",
    "MISSING_VALUE",
    "Found",
    "check_e004",
    "check_e020",
    "check_e021",
    "check_e023",
    "check_e024",
    "check_e035",
    "check_w006",
    "check_w009_stop_time_update",
    "check_w009_trip",
    "is_added_trip",
]

#: What a check hands back: the id upstream logged there and its occurrence
#: prefix, or nothing. The dispatch turns it into an `Event`.
Found = tuple[str, str] | None

#: `TripDescriptor.ScheduleRelationship.ADDED`, the only member `isAddedTrip`
#: names. Under the 2015 schema a post-2015 value never reaches this comparison,
#: because the decoder files it as an unknown field and `has` stays false.
ADDED = 1

#: onebusaway-gtfs 1.3.87 `StopTime.java:30`: the sentinel an unset
#: `arrival_time` reads back as. E023 formats it, and -999 renders "00:-16:-39"
#: under Java's truncating division.
MISSING_VALUE = -999


def is_added_trip(trip: Msg) -> bool:
    """`GtfsUtils.isAddedTrip`, GtfsUtils.java:64-66.

    The `hasScheduleRelationship()` half is what makes the enum gap visible: a
    descriptor carrying a value the 2015 enum does not have answers false here
    and is treated as a scheduled trip by E003 and E016 alike.
    """
    return trip.has("schedule_relationship") and trip.get("schedule_relationship") == ADDED


def check_e004(carrier: Msg, trip: Msg, ctx: RuleContext) -> Found:
    """`checkE004`, `:259-264`. No `hasRouteId()`: `isEmpty` does that work."""
    route_id = trip.get("route_id")
    if route_id != "" and route_id not in ctx.static.route_ids:
        return ("E004", vehicle_and_route_id_text(carrier))
    return None


def check_e020(carrier: Msg, trip: Msg) -> Found:
    """`checkE020`, `:273-278`. Called only under `hasStartTime()`.

    Not enum-sensitive, in either direction: the gates at `:118` and `:167` read
    `hasStartTime()` alone and this body reads `start_time` alone, so no
    schedule_relationship can reach it.
    """
    start_time = trip.get("start_time")
    if not is_valid_time_format(start_time):
        return ("E020", f"{vehicle_and_trip_id_text(carrier)} start_time is {start_time}")
    return None


def check_e021(carrier: Msg, trip: Msg) -> Found:
    """`checkE021`, `:313-319`. The `hasStartDate()` test is inside the helper,
    so the dispatch calls this unconditionally on both vehicle-bearing sides."""
    if not trip.has("start_date") or is_valid_date_format(trip.get("start_date")):
        return None
    start_date = trip.get("start_date")
    return ("E021", f"{vehicle_and_trip_id_text(carrier)} start_date is {start_date}")


def check_e023(carrier: Msg, trip: Msg, ctx: RuleContext) -> Found:
    """`checkE023`, `:287-304`. Element zero of the trip's `stop_times.txt`.

    Frequency-based trips of either kind are exempt, and a trip with no
    stop_times returns rather than reporting: that early return is the fix for
    upstream's issue #217, whose regression case is a valid start_time on a
    trip_id absent from GTFS.

    The Java's `tripId != null` is unreachable in either language, since
    `getTripId()` answers the empty string for an absent field, so it is not
    ported.
    """
    trip_id = trip.get("trip_id")
    static = ctx.static
    if trip_id in static.exact_times_zero_trip_ids or trip_id in static.exact_times_one_trips:
        return None
    stop_times = static.trip_stop_times.get(trip_id)
    if not stop_times:
        return None
    arrival_time = stop_times[0].arrival_time
    formatted = seconds_after_midnight_to_clock(
        MISSING_VALUE if arrival_time is None else arrival_time
    )
    start_time = trip.get("start_time")
    if start_time == formatted:
        return None
    return (
        "E023",
        (
            f"GTFS-rt {vehicle_and_trip_id_text(carrier)} start_time is {start_time} "
            f"and GTFS initial arrival_time is {formatted}"
        ),
    )


def check_e024(carrier: Msg, trip: Msg, ctx: RuleContext) -> Found:
    """`checkE024`, `:329-339`. A string comparison in Java; see the module note.

    A GTFS trip with no `direction_id` always fires when the realtime one is
    present, because `null` fails the `equals` before it is reached, and the
    occurrence then prints the literal "null" that Java's concatenation makes.

    `int directionId = trip.getDirectionId()` (`:331`), so the realtime value is
    the **signed** narrowing before either use: `String.valueOf(directionId)` is
    what the comparison tests and `+ directionId` is what the prefix prints. One
    `int32` at the read covers both, which is the point of narrowing there.

    The other divergence on this field is **not** this one and is not fixed
    here: the sibling types the GTFS column as an enum, so a `trips.txt` cell of
    `00` arrives as `0` and matches a realtime `0`, where the jar compares the
    raw string `"00"` against `"0"` and reports. That is the static layer's, and
    `tests/test_rule_e024.py` carries the measurement, one case per cell.
    """
    if not trip.has("direction_id"):
        return None
    direction_id = int32(trip.get("direction_id"))
    gtfs_trip = ctx.static.trips.get(trip.get("trip_id"))
    if gtfs_trip is None:
        return None
    gtfs_direction_id = gtfs_trip.get("direction_id")
    if gtfs_direction_id is not None and str(gtfs_direction_id) == str(direction_id):
        return None
    printed = "null" if gtfs_direction_id is None else str(gtfs_direction_id)
    return (
        "E024",
        (
            f"GTFS-rt {vehicle_and_trip_id_text(carrier)} trip.direction_id is {direction_id} "
            f"but GTFS trip.direction_id is {printed}"
        ),
    )


def check_e035(entity: Msg, trip: Msg, ctx: RuleContext) -> Found:
    """`checkE035`, `:432-448`. Both early returns defer to another rule.

    An unknown route_id is E004's finding and an unknown trip_id is E003's, so
    this one reports only when both sides exist and disagree. Called from all
    three halves (`:125`, `:174`, `:184`), which is why one entity carrying a
    TripUpdate, a VehiclePosition and an alert can produce three of them.
    """
    if not (trip.has("trip_id") and trip.has("route_id")):
        return None
    route_id = trip.get("route_id")
    if route_id not in ctx.static.route_ids:
        return None
    gtfs_trip = ctx.static.trips.get(trip.get("trip_id"))
    if gtfs_trip is None:
        return None
    gtfs_route_id = gtfs_trip["route_id"]
    if gtfs_route_id == route_id:
        return None
    return (
        "E035",
        (
            f"GTFS-rt entity ID {entity.get('id')} trip_id {trip.get('trip_id')} "
            f"has route_id {route_id} but belongs to GTFS route_id {gtfs_route_id}"
        ),
    )


def check_w006(entity: Msg, trip: Msg) -> Found:
    """`checkW006`, `:457-461`. Java's `tripDescriptor != null` is unreachable
    here: an absent sub-message reads back as the default instance."""
    if trip.has("trip_id"):
        return None
    return ("W006", f"entity ID {entity.get('id')}")


def check_w009_trip(entity: Msg, trip: Msg) -> Found:
    """`checkW009(FeedEntity, TripDescriptor)`, `:470-474`.

    Enum-sensitive by construction: `hasScheduleRelationship()` is false for a
    post-2015 value under the 2015 schema, so such a trip is warned about as if
    the field were absent.
    """
    if trip.has("schedule_relationship"):
        return None
    return ("W009", trip_descriptor_id_text(entity, trip))


def check_w009_stop_time_update(entity: Msg, stop_time_update: Msg) -> Found:
    """`checkW009(FeedEntity, StopTimeUpdate)`, `:483-487`.

    The trip half of the prefix is read off `entity.getTripUpdate().getTrip()`
    rather than off anything passed in, which is why this overload takes the
    entity and not the TripUpdate.
    """
    if stop_time_update.has("schedule_relationship"):
        return None
    trip = entity.get("trip_update").get("trip")
    return (
        "W009",
        (
            f"{trip_descriptor_id_text(entity, trip)} "
            f"{stop_time_update_id_text(stop_time_update)} (and potentially more for this trip)"
        ),
    )
