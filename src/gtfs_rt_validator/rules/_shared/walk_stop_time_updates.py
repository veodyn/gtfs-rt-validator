"""`StopTimeUpdateValidator.java:79-198`: one pass, twelve reported ids.

The walk `_shared/walks.py` was designed for. Twelve rule modules read this one
stream, and the reason none of them may loop on its own is `:180`: a
stop_time_update naming a stop_sequence no `stop_times.txt` row of that trip
carries logs E051 and `break`s, abandoning the rest of that trip for **every**
rule in the validator. A rule looping independently keeps going and reports
findings the jar never reaches.

Only TripUpdate entities are examined (`:76-77`). VehiclePositions and alerts
are ignored entirely.

**Every stop_sequence is read through `javafmt.int32`.** `getStopSequence()`
returns a Java `int`, so a `uint32` above 2^31-1 is negative to every line of
this validator: the two accumulator lists, `previousRtStopSequence`, the match
against a GTFS row, and the text. Narrowing at the read rather than at the
render is what makes `_strictly_ordered` and `_advance` agree with the jar; a
feed sending 1 then 4294967295 is `[1, -1]` upstream and gets an E002 that an
unsigned comparison misses entirely.

Five things a port gets wrong, all of them measurable and all of them tested in
`tests/test_shared_walk_stop_time_updates.py`:

1. **`checkE041` runs before anything else** per TripUpdate (`:79`), ahead of
   the trip_id lookup.
2. **`previousRtStopSequence` and `previousRtStopId` take the unguarded
   getters** (`:111-112`), so they become 0 and `""` for an absent field, while
   the two accumulator lists append only under `hasStopSequence()` /
   `hasStopId()` (`:113-118`). Adjacent lines, different conditions.
3. **The `while` loop never rewinds.** `_advance` below walks
   `gtfsStopTimeIndex` forward through the trip's rows and picks up where it
   left off on the next stop_time_update, which is what makes the validator
   O(n + m) rather than O(n * m). A gap in the feed's stop_sequences therefore
   consumes GTFS rows that a later stop_time_update can then never match.
4. **The index is incremented before the break tests** (`:143`), so the stop-id
   branch re-reads `gtfsStopTimeIndex - 1`. That is the row the loop just
   examined, and reading `gtfsStopTimeIndex` instead silently asks E046 about
   the next stop.
5. **The E051 flag is only ever set on the last GTFS row** (`:148-151`). A bad
   stop_sequence in the middle of a trip is not detected where it sits: the walk
   consumes the whole of `stop_times.txt` first, and only the reported
   stop_sequence says which one was wrong.

E002 runs after the loop (`:184-198`), over lists the loop accumulated, and its
verdict is therefore computed from a truncated list when the break fired.

The `checkEXXX` methods this calls are `stop_time_update_checks.py`, split there
along upstream's own seam between the stateful loop and the stateless checks.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.ids import trip_id_text
from gtfs_rt_validator.rules._shared.javafmt import int32, java_list
from gtfs_rt_validator.rules._shared.stop_time_update_checks import (
    StopTime,
    check_e036,
    check_e037,
    check_e040,
    check_e041,
    check_e042,
    check_e043,
    check_e044,
    check_e045,
    check_e046,
)
from gtfs_rt_validator.rules._shared.walks import Event, events_for

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["occurrences_for", "stop_time_updates"]


def stop_time_updates(message: Msg, ctx: RuleContext) -> Iterator[Event]:
    """Every event this validator's twelve rules can report, in emission order."""
    for index, entity in enumerate(message.get("entity")):
        if entity.has("trip_update"):
            path = f"entity[{index}].trip_update"
            yield from _trip_update(entity, entity.get("trip_update"), ctx, path)


def occurrences_for(rule_id: str, message: Msg, ctx: RuleContext) -> list[Occurrence]:
    """This walk's events for one rule, as that rule's occurrences.

    Twelve modules would otherwise carry the same four lines. Each still owns
    its id, its docstring and its registration; what it does not own is the
    filter, which is the walk's business.
    """
    return [
        Occurrence(rule_id, event.prefix, event.context)
        for event in events_for(rule_id, stop_time_updates, message, ctx)
    ]


@dataclass(slots=True)
class _Scan:
    """`gtfsStopTimeIndex` and the two flags the `while` loop sets.

    One per TripUpdate, and only when the trip was found in `stop_times.txt`:
    `gtfsStopTimes` stays null otherwise (`:80-86`) and the whole loop is
    skipped, which is why E045, E046 and E051 are unreachable for a TripUpdate
    with no trip_id or an unknown one.
    """

    rows: Sequence[StopTime]
    index: int = 0
    unknown_stop_sequence: bool = False
    added_stop_sequence_from_stop_id: bool = False
    recovered: list[int] = field(default_factory=list)


def _trip_update(entity: Msg, trip_update: Msg, ctx: RuleContext, path: str) -> Iterator[Event]:
    """`:77-198`, one TripUpdate, in the Java's own order."""
    yield from check_e041(entity, trip_update, path)

    trip_id: str | None = None
    scan: _Scan | None = None
    trip = trip_update.get("trip")
    if trip_update.has("trip") and trip.has("trip_id"):
        trip_id = trip.get("trip_id")
        rows = ctx.static.trip_stop_times.get(trip_id)
        scan = None if rows is None else _Scan(rows)

    updates = trip_update.get("stop_time_update")
    stop_sequences: list[int] = []
    stop_ids: list[str] = []
    previous_stop_sequence: int | None = None
    previous_stop_id: str | None = None
    found_e009 = False
    multi_stop = ctx.static.trips_with_multi_stops

    for position, update in enumerate(updates):
        at = f"{path}.stop_time_update[{position}]"
        if (
            not found_e009
            and trip_id is not None
            and trip_id in multi_stop
            and not update.has("stop_sequence")
        ):
            visited = java_list(multi_stop[trip_id])
            yield Event(
                "E009", f"trip_id {trip_id} visits stop_id {visited}", {ENTITY_PATH_KEY: at}
            )
            found_e009 = True  # Only log once for this entity, not for this trip_id: the
            # flag is declared inside the entity loop (`:94`), so two TripUpdate entities
            # naming one trip_id each report.
        if previous_stop_sequence is not None:
            yield from check_e036(entity, previous_stop_sequence, update, at)
        if previous_stop_id is not None:
            yield from check_e037(entity, previous_stop_id, update, at)
        previous_stop_sequence = int32(update.get("stop_sequence"))
        previous_stop_id = update.get("stop_id")
        if update.has("stop_sequence"):
            stop_sequences.append(int32(update.get("stop_sequence")))
        if update.has("stop_id"):
            stop_ids.append(update.get("stop_id"))
        if scan is not None:
            yield from _advance(scan, entity, trip_update, update, at)
            stop_sequences.extend(scan.recovered)
        yield from check_e040(entity, trip_update, update, at)
        yield from check_e042(entity, trip_update, update, at)
        yield from check_e043(entity, trip_update, update, at)
        yield from check_e044(entity, trip_update, update, at)
        if scan is not None and scan.unknown_stop_sequence:
            trip_text = trip_id_text(entity, trip_update)
            sequence = int32(update.get("stop_sequence"))
            yield Event(
                "E051",
                f"GTFS-rt {trip_text} contains stop_sequence {sequence}",
                {ENTITY_PATH_KEY: at},
            )
            break

    yield from _check_e002(entity, trip_update, stop_sequences, stop_ids, len(updates), scan, path)


def _advance(scan: _Scan, entity: Msg, trip_update: Msg, update: Msg, path: str) -> Iterator[Event]:
    """`:119-166`, the `while` loop, for one stop_time_update.

    `scan.recovered` is how the stop_sequence the stop-id branch recovers from
    GTFS (`:155`) reaches `rtStopSequenceList`, which lives a level up. It is a
    list rather than an optional because the caller extends with it
    unconditionally; the loop can only ever put one value in it, since the
    branch that fills it also breaks.
    """
    scan.recovered.clear()
    has_stop_sequence = update.has("stop_sequence")
    has_stop_id = update.has("stop_id")
    while scan.index < len(scan.rows):
        row = scan.rows[scan.index]
        gtfs_stop_sequence = row.stop_sequence
        gtfs_stop_id = row.stop_id
        found_stop_sequence = False
        found_stop_id = False
        if has_stop_sequence and gtfs_stop_sequence == int32(update.get("stop_sequence")):
            yield from check_e045(
                entity, trip_update, update, gtfs_stop_sequence, gtfs_stop_id, path
            )
            yield from check_e046(entity, trip_update, update, row, path)
            found_stop_sequence = True
        if has_stop_id and gtfs_stop_id == update.get("stop_id"):
            # Not a definitive match the way a stop_sequence is: a route with a
            # loop visits one stop twice. Upstream's comment at `:136-139`.
            found_stop_id = True
        scan.index += 1
        if found_stop_sequence:
            # Caught up with GTFS, so leave the index here for the next
            # stop_time_update rather than rewinding.
            break
        if has_stop_sequence and scan.index == len(scan.rows):
            # `:148-151`, upstream issue #261. Only ever set on the last row.
            scan.unknown_stop_sequence = True
        if not has_stop_sequence and found_stop_id:
            # `:152-164`, upstream issue #159. The inner `if (!stu.hasStopSequence())`
            # at `:154` is redundant with the branch it sits in and is dropped.
            scan.recovered.append(gtfs_stop_sequence)
            scan.added_stop_sequence_from_stop_id = True
            # `gtfsStopTimeIndex - 1` at `:160`, which is `row` above: the
            # increment two lines up already happened. Written as the Java writes
            # it so the two read the same.
            yield from check_e046(entity, trip_update, update, scan.rows[scan.index - 1], path)
            break


def _check_e002(
    entity: Msg,
    trip_update: Msg,
    stop_sequences: Sequence[int],
    stop_ids: Sequence[str],
    update_count: int,
    scan: _Scan | None,
    path: str,
) -> Iterator[Event]:
    """`:184-198`, after the loop. Two mutually exclusive forms.

    `update_count` is the whole `getStopTimeUpdateList().size()`, which the break
    does not shorten, so a trip cut short by E051 compares a truncated list of
    stop_sequences against the full count. Guava's `isStrictlyOrdered` means
    strictly increasing, so a repeated value is unsorted and a list of nought or
    one is sorted.
    """
    trip = trip_id_text(entity, trip_update)
    if not _strictly_ordered(stop_sequences):
        prefix = f"{trip} stop_sequence {java_list(stop_sequences)}"
    elif (
        scan is not None
        and scan.added_stop_sequence_from_stop_id
        and len(stop_sequences) < update_count
    ):
        # At least one stop_time_update was not found in GTFS by stop_id, so the
        # ones that were cannot vouch for the order of the ones that were not.
        prefix = f"{trip} stop_sequence for stop_ids {java_list(stop_ids)}"
    else:
        return
    yield Event("E002", prefix, {ENTITY_PATH_KEY: path})


def _strictly_ordered(values: Sequence[int]) -> bool:
    """`Ordering.natural().isStrictlyOrdered`, which is strictly increasing.

    Over `List<Integer>`, so over the **signed** narrowing of each stop_sequence.
    The list is built from `int32` above for exactly this reason: a feed sending
    1 then 4294967295 is `[1, -1]` to Java, which is not strictly ordered, and
    the jar emits an E002 that a comparison on the unsigned values would miss.
    """
    return all(earlier < later for earlier, later in pairwise(values))
