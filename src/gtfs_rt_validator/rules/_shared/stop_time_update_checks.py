"""The eight `checkEXXX` methods of `StopTimeUpdateValidator`, one per function.

Split from `walk_stop_time_updates.py` along upstream's own seam: everything
here is a private method of `StopTimeUpdateValidator.java` that takes a
stop_time_update and appends to one list, and everything there is the stateful
loop that decides when to call them. The loop is what a rule may not
reimplement; these are what it calls.

Each function is a generator yielding `Event`s rather than appending to a list,
because that is what a walk yields, and each one takes the entity path its
caller computed: the walk knows where it is and none of these do.

**Enum values are written as numbers, and the numbers are checked by a test.**
A rule module may be handed a message decoded under either the 2015 or the
current schema, so a name-to-number lookup here would have to know which, and
`Msg` does not expose its schema. Protobuf enum numbers are frozen by the wire
format, so `SKIPPED`, `NO_DATA` and `CANCELED` mean the same number in both;
`tests/test_shared_walk_stop_time_updates_stream.py` asserts that against both
generated schema modules rather than taking it on trust. What a rule must never
do is compare against a *name*: under the 2015 schema a post-2015 value is not
in the enum at all, `has("schedule_relationship")` is false, and every check
below therefore behaves as though the field were absent. That is the whole
point of decoding twice.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.ids import stop_time_update_id_text, trip_id_text
from gtfs_rt_validator.rules._shared.javafmt import int32, int32_str
from gtfs_rt_validator.rules._shared.walks import Event


class StopTime(Protocol):
    """One `stop_times.txt` row as `StaticContext` holds it.

    Spelled structurally rather than imported from `static._stoptimes`, because
    nothing under `rules/` may reach the static layer at run time. It was a
    `Mapping[str, Any]` while the context held loaded dicts; it is these four
    attributes now that the context holds a record instead, and a `Protocol`
    keeps the direction of the dependency the same either way.
    """

    stop_sequence: int
    stop_id: str
    arrival_time: int | None
    departure_time: int | None


__all__ = [
    "CANCELED",
    "NO_DATA",
    "SKIPPED",
    "StopTime",
    "check_e036",
    "check_e037",
    "check_e040",
    "check_e041",
    "check_e042",
    "check_e043",
    "check_e044",
    "check_e045",
    "check_e046",
]

#: `TripUpdate.StopTimeUpdate.ScheduleRelationship`.
SKIPPED = 1
NO_DATA = 2

#: `TripDescriptor.ScheduleRelationship`, a different enum with its own numbers.
CANCELED = 3

RELATIONSHIP = "schedule_relationship"


def _at(path: str) -> dict[str, object]:
    return {ENTITY_PATH_KEY: path}


def check_e036(entity: Msg, previous_stop_sequence: int, update: Msg, path: str) -> Iterator[Event]:
    """`checkE036`, `:251-257`. Sequential stop_time_updates repeat a stop_sequence.

    `previousStopSequence` is an `Integer` and `getStopSequence()` an `int`, so
    Java unboxes and compares numerically. The previous value was stored without
    a presence guard (`:111`), so an absent stop_sequence stored 0 and an
    explicit stop_sequence 0 after it fires.

    Both sides are the **signed** narrowing, which is what `getStopSequence()`
    returns. `previous_stop_sequence` was narrowed by the walk when it stored it
    (`:111`); this one is narrowed here. Equality happens to survive the
    narrowing either way, so this pair alone would have been safe unconverted,
    but a field read one way in one check and another way in the next is how the
    two drift apart.

    The prefix re-fetches the TripUpdate off the entity rather than using a
    parameter, which is `GtfsUtils.getTripId(entity, entity.getTripUpdate())`.
    Same object, and ported as written.
    """
    if update.has("stop_sequence") and previous_stop_sequence == int32(update.get("stop_sequence")):
        trip = trip_id_text(entity, entity.get("trip_update"))
        yield Event(
            "E036",
            f"{trip} has repeating stop_sequence {int32_str(previous_stop_sequence)}",
            _at(path),
        )


def check_e037(entity: Msg, previous_stop_id: str, update: Msg, path: str) -> Iterator[Event]:
    """`checkE037`, `:268-282`. Sequential stop_time_updates repeat a stop_id.

    The `!previousStopId.isEmpty()` guard is what stops the empty string stored
    for an absent stop_id (`:112`) from matching another absent one. The
    `at stop_sequence` clause is appended only when this update has one, which
    is a `StringBuilder` in the Java and a conditional suffix here.
    """
    if previous_stop_id and update.has("stop_id") and previous_stop_id == update.get("stop_id"):
        trip = trip_id_text(entity, entity.get("trip_update"))
        prefix = f"{trip} has repeating stop_id {previous_stop_id}"
        if update.has("stop_sequence"):
            prefix += f" at stop_sequence {int32_str(update.get('stop_sequence'))}"
        yield Event("E037", prefix, _at(path))


def check_e040(entity: Msg, trip_update: Msg, update: Msg, path: str) -> Iterator[Event]:
    """`checkE040`, `:292-296`. Neither stop_id nor stop_sequence.

    The prefix identifies the *trip*, not the stop_time_update, so several bare
    stop_time_updates on one trip produce several identical strings.
    """
    if not update.has("stop_sequence") and not update.has("stop_id"):
        yield Event("E040", trip_id_text(entity, trip_update), _at(path))


def check_e041(entity: Msg, trip_update: Msg, path: str) -> Iterator[Event]:
    """`checkE041`, `:305-315`. A trip with no stop_time_updates that is not CANCELED.

    The exemption needs `hasScheduleRelationship()` *and* the recognised value
    CANCELED, which is in the 2015 enum, so it works the same under both
    schemas. What differs is a post-2015 value such as DUPLICATED: under the
    2015 schema it is not in the enum, `hasScheduleRelationship()` is false, and
    the trip is reported. It never qualified for the exemption under either
    schema, so nothing is lost, but a feed carrying one does get E041.
    """
    if len(trip_update.get("stop_time_update")) >= 1:
        return
    trip = trip_update.get("trip")
    if trip_update.has("trip") and trip.has(RELATIONSHIP) and trip.get(RELATIONSHIP) == CANCELED:
        return
    yield Event("E041", trip_id_text(entity, trip_update), _at(path))


def check_e042(entity: Msg, trip_update: Msg, update: Msg, path: str) -> Iterator[Event]:
    """`checkE042`, `:325-337`. An arrival or a departure on a NO_DATA update.

    Two independent tests, not an either-or: a NO_DATA stop_time_update carrying
    both gives two occurrences.
    """
    if not (update.has(RELATIONSHIP) and update.get(RELATIONSHIP) == NO_DATA):
        return
    prefix = f"{trip_id_text(entity, trip_update)} {stop_time_update_id_text(update)}"
    if update.has("arrival"):
        yield Event("E042", f"{prefix} has arrival", _at(path))
    if update.has("departure"):
        yield Event("E042", f"{prefix} has departure", _at(path))


def check_e043(entity: Msg, trip_update: Msg, update: Msg, path: str) -> Iterator[Event]:
    """`checkE043`, `:347-357`. Neither an arrival nor a departure.

    SKIPPED and NO_DATA are both exempt here. E044 below exempts only SKIPPED,
    which is the one asymmetry between the two rules.
    """
    if update.has("arrival") or update.has("departure"):
        return
    if update.has(RELATIONSHIP) and update.get(RELATIONSHIP) in (SKIPPED, NO_DATA):
        return
    prefix = f"{trip_id_text(entity, trip_update)} {stop_time_update_id_text(update)}"
    yield Event("E043", prefix, _at(path))


def check_e044(entity: Msg, trip_update: Msg, update: Msg, path: str) -> Iterator[Event]:
    """`checkE044`, `:368-393`. An arrival or departure with neither delay nor time.

    SKIPPED returns early (upstream issue #243); NO_DATA does not, unlike E043.
    """
    if update.has(RELATIONSHIP) and update.get(RELATIONSHIP) == SKIPPED:
        return
    prefix = f"{trip_id_text(entity, trip_update)} {stop_time_update_id_text(update)}"
    for field in ("arrival", "departure"):
        if not update.has(field):
            continue
        event = update.get(field)
        if not event.has("delay") and not event.has("time"):
            yield Event("E044", f"{prefix} {field}", _at(path))


def check_e045(
    entity: Msg,
    trip_update: Msg,
    update: Msg,
    gtfs_stop_sequence: int,
    gtfs_stop_id: str,
    path: str,
) -> Iterator[Event]:
    """`checkE045`, `:405-413`. The matched GTFS row names a different stop_id.

    Reached only from the stop_sequence match inside the walk, so
    `stu.getStopSequence()` and `gtfsStopSequence` are always equal in the
    rendered text even though the Java interpolates both. `stop.getId().getId()`
    is the bare stop_id, never the `agencyId_id` compound.

    `int32_str` on the realtime stop_sequence and **not** on `gtfs_stop_sequence`,
    which is a `stop_times.txt` cell onebusaway already holds as an `int` and
    that nothing widened. The two are equal whenever this runs, since the walk
    calls it only on a match, and that match is now made on the narrowed value
    too: a feed sending 4294967295 matches a GTFS row of -1 in the jar, and it
    matches one here.
    """
    if not update.has("stop_id") or gtfs_stop_id == update.get("stop_id"):
        return
    trip = f"GTFS-rt {trip_id_text(entity, trip_update)} "
    stop_sequence = f"stop_sequence {int32_str(update.get('stop_sequence'))}"
    stop_id = f"stop_id {update.get('stop_id')}"
    summary = f" but GTFS stop_sequence {gtfs_stop_sequence} has stop_id {gtfs_stop_id}"
    yield Event("E045", f"{trip}{stop_sequence} has {stop_id}{summary}", _at(path))


def check_e046(
    entity: Msg, trip_update: Msg, update: Msg, row: StopTime, path: str
) -> Iterator[Event]:
    """`checkE046`, `:424-440`. A time-less arrival or departure over a blank GTFS cell.

    **Neither condition tests `hasDelay()`.** This rule is easily read as "the
    producer sent only a delay", and `:428` and `:434` say
    `!getArrival().hasTime() && !gtfsStopTime.isArrivalTimeSet()` with no
    mention of delay, so a `StopTimeEvent` carrying nothing at all reports here
    as well as at E044.

    `isArrivalTimeSet()` in onebusaway-gtfs 1.3.87 is `arrivalTime != -999`, the
    sentinel for a blank cell. The sibling's loader gives `None` for the same
    cell, so `row.arrival_time is None` is the same question.
    """
    prefix = f"GTFS-rt {trip_id_text(entity, trip_update)} {stop_time_update_id_text(update)} "
    scheduled = (("arrival", row.arrival_time), ("departure", row.departure_time))
    for field, cell in scheduled:
        if not update.has(field):
            continue
        if not update.get(field).has("time") and cell is None:
            yield Event("E046", f"{prefix}{field}.time", _at(path))
