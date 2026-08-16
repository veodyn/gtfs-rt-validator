"""S006: an update giving one time where `stop_times.txt` gives two.

`:240`, the sentence after E043's. E043 reports an update with **neither**
arrival nor departure; this reports an update with **exactly one** where the
schedule has both. The two bands cannot overlap, which is why `OVERLAP` in
`tests/test_tier_overlap.py` records E043 as this rule's one permitted
neighbour, and `tests/test_rule_s006.py` asserts the disjointness in both
directions.

**Scoped to SCHEDULED, because the clause is inside that member's comment.**
The other two members of `StopTimeUpdate.ScheduleRelationship` relax the same
requirement in their own words: SKIPPED says "Arrival and departure are
optional" (`:246`) and NO_DATA says "Neither arrival nor departure should be
supplied" (`:250`). A rule that fired on those would contradict the sentences
next to the one it cites, and over-firing is the failure mode a tier with no
oracle ships.

**Matching an update to a GTFS row.** By `stop_sequence` when the update gives
one, by `stop_id` otherwise, which is the pairing `:222` and `:224` describe.
An update that matches no row says nothing here: a stop_sequence `stop_times.txt`
does not carry is E051's, a stop_id mismatch is E045's, and a trip absent from
GTFS is E003's. This rule is about the times, and it needs a row to read them
from.

Both schedule times are `int` seconds or `None` from the loader, so "the
schedule contains both" is two `is not None` tests rather than anything about
formatting.

## The terminal stops are excused, and that is a narrowing of the clause

Measured over six recorded MBTA TripUpdates messages, this rule produced 6723
occurrences on 674 of 793 trips per message. Matched against the archive's
`stop_times.txt`, every one-sided SCHEDULED update in the sample was at an end
of its own trip: 473 were the trip's first stop giving a departure only and 652
its last stop giving an arrival only, with **none in the middle**. A trip's
first stop has no arrival to predict and its last stop has no departure, so
those 1125 updates were a producer doing the right thing.

The clause's antecedent is about what `stop_times.txt` contains, and it does
contain both times at a terminal: GTFS wants `arrival_time` and
`departure_time` together or not at all, so the static feed cannot distinguish
"the vehicle arrives here at 09:00" from "there is no arrival here". Read
literally, the sentence therefore asks for a departure at the last stop of
every trip. That reading is what produced the 6723, and this rule declines it.
The exemption is recorded as a narrowing on `240#2` in
`upstream/spec-clause-verdicts.json` rather than argued into the sentence.

**The exemption is asymmetric, because the defect it must not swallow is.** A
first stop is excused the *arrival* alone; withhold its departure and it is
still reported. A last stop is excused the *departure* alone. A symmetric "any
terminal, either event" exemption would silence a genuine defect at a terminal,
and the measured shape is exactly the asymmetric one. A trip of a single stop is
both terminals at once and is excused both ways: it has no journey between stops
for either event to be about.

**Where the position cannot be decided, the rule is silent.** The position is
the matched row's index in the trip's sorted rows, so an update naming a
`stop_sequence` always decides it. An update naming only a `stop_id` decides it
only when the trip visits that stop once; on a loop route it does not, and this
returns nothing rather than guessing. Silence is the deliberate answer: the
first-match row a guess would read is already the wrong row's times, and
over-firing is the failure mode a tier with no oracle ships. Best Practices
`:95` asks producers for `stop_sequence` for this exact reason.

That second narrowing was measured rather than assumed, because it is the kind
that quietly costs coverage: over the same recording it silences **nothing**.
The count is 0 with the guard and 0 without it, so every one of the 6723 was
excused by the terminal exemption alone and no MBTA occurrence turned on a
repeated stop_id at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import (
    STOP_TIME_SCHEDULED,
    relationships,
)
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from collections.abc import Mapping, Sequence

    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import (
        StopTimeRelationship,
        TripRelationship,
    )
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S006"

CLAUSE = (
    "If the schedule for this stop contains both arrival and departure times then so must "
    "this update."
)

ONLY_ONE = "trip_id {trip_id} {stop} gives only {given} where stop_times.txt gives both times"

SCHEDULE_TIMES = ("arrival_time", "departure_time")

ARRIVAL, DEPARTURE = "arrival", "departure"

EVENTS = (ARRIVAL, DEPARTURE)


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per SCHEDULED update that answered a two-time row with one."""
    return [
        found
        for record in relationships(message, ctx)
        if record.payload == "trip_update"
        for found in _of_trip(record, ctx)
    ]


def _of_trip(record: TripRelationship, ctx: RuleContext) -> list[Occurrence]:
    trip = record.trip
    if not trip.has("trip_id"):
        return []
    trip_id = trip.get("trip_id")
    rows = ctx.static.trip_stop_times.get(trip_id)
    if not rows:
        return []
    revisited = frozenset(ctx.static.trips_with_multi_stops.get(trip_id, ()))
    return [
        found
        for stop_time in record.stop_time_updates
        if stop_time.relationship == STOP_TIME_SCHEDULED
        for found in _of_update(trip_id, stop_time, rows, revisited)
    ]


def _of_update(
    trip_id: str,
    stop_time: StopTimeRelationship,
    rows: Sequence[Mapping[str, Any]],
    revisited: frozenset[str],
) -> list[Occurrence]:
    position = _position_of(stop_time.update, rows, revisited)
    if position is None:
        return []
    row = rows[position]
    if any(row.get(name) is None for name in SCHEDULE_TIMES):
        return []
    given = [event for event in EVENTS if stop_time.update.has(event)]
    if len(given) != 1 or _at_a_terminal(given[0], position, len(rows)):
        return []
    return [
        Occurrence(
            RULE_ID,
            ONLY_ONE.format(trip_id=trip_id, stop=_stop_text(stop_time.update), given=given[0]),
            {ENTITY_PATH_KEY: stop_time.path, "tripId": trip_id, "given": given[0]},
        )
    ]


def _position_of(
    update: Msg, rows: Sequence[Mapping[str, Any]], revisited: frozenset[str]
) -> int | None:
    """Where in the trip this update sits, by sequence then by id, or `None`.

    An index rather than the row itself, because the row alone cannot say
    whether it is an end of the trip and `rows.index(row)` on a loop route would
    answer for the wrong visit. `None` covers four cases the caller treats
    alike: the update names neither field, it names a `stop_sequence` no row
    carries (E051's), it names a `stop_id` no row carries (E045's), and it names
    a `stop_id` the trip visits more than once, where the position is
    undecidable and the docstring above says why that is silence.
    """
    if update.has("stop_sequence"):
        wanted = update.get("stop_sequence")
        return next((at for at, row in enumerate(rows) if row.get("stop_sequence") == wanted), None)
    if update.has("stop_id"):
        wanted = update.get("stop_id")
        if wanted in revisited:
            return None
        return next((at for at, row in enumerate(rows) if row.get("stop_id") == wanted), None)
    return None


def _at_a_terminal(given: str, position: int, total: int) -> bool:
    """Is the event this one-sided update omitted one the trip never has here?

    `given` is the single event the update did supply, so the omitted one is the
    other. Omitting the arrival is excused at the trip's first stop and nowhere
    else; omitting the departure is excused at its last. A one-stop trip
    satisfies both tests, which is the intended answer.
    """
    if given == DEPARTURE:
        return position == 0
    return position == total - 1


def _stop_text(update: Msg) -> str:
    """Which stop the occurrence names, in whichever way the update named it."""
    if update.has("stop_sequence"):
        return f"stop_sequence {update.get('stop_sequence')}"
    return f"stop_id {update.get('stop_id')}"
