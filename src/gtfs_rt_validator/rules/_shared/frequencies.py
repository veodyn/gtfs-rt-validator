"""frequencies.txt as the two frequency validators read it, and the loop that spins.

`FrequencyTypeZeroValidator` (E006, E013, W005) and `FrequencyTypeOneValidator`
(E019) are four rule modules over two Java files, and what they share is not
occurrence text but *control flow*: which halves of an entity are in scope, and
how a period's `start_time` is stepped by `headway_secs`. Copying either into
four modules would copy the two things that are easy to get subtly wrong.

**The exact_times = 0 gate is asymmetric, and deliberately so.** The TripUpdate
half (`FrequencyTypeZeroValidator.java:55`) has no `hasTrip()` and no
`hasTripId()` guard, so a TripUpdate whose descriptor carries no trip_id looks
`""` up in the set; the VehiclePosition half (`:83-84`) guards on `hasTrip()`
first. Upstream's own comment at `:56-58` says why it does not care: missing
trip_ids are W006's problem, and this validator needs the trip_id before it can
know whether the trip is frequency-based at all. No GTFS archive can hold a
frequencies row whose trip_id is the empty string, so the difference is
unobservable through the jar; it is reproduced because the two halves are
written differently and a port that guarded both would be guessing.

**`start_times` is `FrequencyTypeOneValidator`'s `while` loop, and upstream's
does not always terminate.** `startTime += f.getHeadwaySecs()` never advances on
a `headway_secs` of zero, and the loop condition never changes, so the jar spins
on the main thread until it is killed: measured at 12.1 seconds of CPU in 12.2
seconds of wall clock with `jstack` naming `FrequencyTypeOneValidator.java:64`,
and no results file written for that feed or any after it, in a run whose
realtime message named that trip. `runner/gate.py` approximates that outcome by
refusing the feed, which is the one place that already chooses between refusing
a run and recording a system error; nothing here raises, and `cannot_advance` is
the question that gate asks. It is an over-approximation, since the jar enters
the loop only for a trip a message names, and a feed that names other trips is
one the jar completes.

The generator below still has to terminate for the run that carries on, so it
yields the one candidate the first iteration would have produced and stops.
Measured: the sibling will not load such a row at all today, so nothing in a
real run reaches either the guard or that early return, and the archive is
refused at load with no output in either mode where the jar would have written
some. `tests/test_shared_frequencies.py` pins that divergence and says why both
the guard and the early return stay.

Field types are the sibling loader's: a GTFS TIME is an `int` of seconds after
midnight, past-midnight preserved, and an absent cell is `None`. onebusaway's
`Frequency` holds all three as primitive `int`s, so `None` reads as 0 here, the
same way `GtfsMetadata` sees a blank `exact_times` as 0.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator, Mapping
from typing import TYPE_CHECKING

from gtfs_rt_validator.rules._shared.ids import vehicle_and_trip_id_text

if TYPE_CHECKING:  # Type-only: nothing under `rules/` imports the runner at run time.
    from gtfs_rt_validator.proto.decode import Msg

__all__ = [
    "TRIP_UPDATE",
    "VEHICLE_POSITION",
    "cannot_advance",
    "end_time",
    "frequency_zero_halves",
    "half_id_text",
    "headway_secs",
    "start_time",
    "start_times",
    "trip_id_text",
]

#: `Msg.desc.name` for the two halves `frequency_zero_halves` yields, so a rule
#: can tell them apart the way `_shared/ids.py` does.
TRIP_UPDATE = "TripUpdate"
VEHICLE_POSITION = "VehiclePosition"

Row = Mapping[str, object]


def _seconds(value: object) -> int:
    """One `Frequency` field as onebusaway holds it: a primitive `int`."""
    return value if isinstance(value, int) else 0


def start_time(row: Row) -> int:
    return _seconds(row.get("start_time"))


def end_time(row: Row) -> int:
    return _seconds(row.get("end_time"))


def headway_secs(row: Row) -> int:
    return _seconds(row.get("headway_secs"))


def cannot_advance(row: Row) -> bool:
    """Whether upstream's `while` loop would never terminate on this period.

    Both halves matter. A non-positive headway cannot advance `startTime`, and
    a period whose `start_time` is not before its `end_time` never enters the
    loop at all, so a zero headway there is harmless: the jar walks straight
    past it and reports two `null`s.
    """
    return start_time(row) < end_time(row) and headway_secs(row) <= 0


def start_times(row: Row) -> Iterator[int]:
    """Every candidate `FrequencyTypeOneValidator` tries for one period.

    `for (int t = f.getStartTime(); t < f.getEndTime(); t += f.getHeadwaySecs())`
    written as a generator, so both branches share the stepping and differ only
    in how they render each candidate. `end_time` is exclusive: a period of
    06:00:00 to 10:00:01 with a 3600-second headway ends at 10:00:00, which is
    the value that reaches the occurrence.

    A period `cannot_advance` returns true for yields its first candidate and
    stops rather than spinning. See the module docstring for what upstream does
    instead and for why nothing here treats it as an error.
    """
    current = start_time(row)
    finish = end_time(row)
    headway = headway_secs(row)
    while current < finish:
        yield current
        if headway <= 0:
            return
        current += headway


def frequency_zero_halves(message: Msg, trip_ids: Collection[str]) -> Iterator[tuple[Msg, Msg]]:
    """`(entity, half)` for every half of `FrequencyTypeZeroValidator`'s one pass.

    The half is the TripUpdate or the VehiclePosition itself, in the order the
    Java writes them: within an entity the TripUpdate first, and entities in
    feed order. Measured against the jar with two entities, which reports
    entity one's two halves before entity two's rather than every TripUpdate
    first. The entity travels with the half because W005's VehiclePosition
    prefix names it.
    """
    for entity in message.get("entity"):
        if entity.has("trip_update"):
            trip_update = entity.get("trip_update")
            # `:55`, unguarded: an absent trip_id looks up "". See the docstring.
            if trip_update.get("trip").get("trip_id") in trip_ids:
                yield entity, trip_update
        if entity.has("vehicle"):
            position = entity.get("vehicle")
            # `:83-84`, and the `hasTrip()` guard is on this side only.
            if position.has("trip") and position.get("trip").get("trip_id") in trip_ids:
                yield entity, position


def trip_id_text(half: Msg) -> str:
    """`"trip_id " + x.getTrip().getTripId()`, which all three type-zero rules open with.

    Not `_shared/ids.trip_descriptor_id_text`: that one falls back to the feed
    entity's id when the descriptor carries no trip_id, and this validator never
    does, so a trip_id-less descriptor gives `"trip_id "` with the space.
    """
    return "trip_id " + half.get("trip").get("trip_id")


def half_id_text(half: Msg) -> str:
    """What E006 and E013 open their prefix with, whichever half they are on.

    `"trip_id X"` for a TripUpdate (`:61`, `:66`, `:71`) and
    `"vehicle_id V trip_id X"` for a VehiclePosition (`:91`, `:96`, `:101`).
    The VehiclePosition form is `GtfsUtils.getVehicleAndTripIdText`'s to the
    byte, though the Java inlines the concatenation rather than calling it, and
    sharing that helper is what keeps one copy of a string with an unguarded
    `getId()` in the middle of it. W005 is not here: its two halves share no
    text at all.
    """
    if half.desc.name == TRIP_UPDATE:
        return trip_id_text(half)
    return vehicle_and_trip_id_text(half)
