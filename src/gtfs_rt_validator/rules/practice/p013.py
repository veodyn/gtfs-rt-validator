"""P013: `StopTimeEvent.delay` on a stop_time_update of an exact_times=0 trip.

`:141`. A `frequencies.txt` trip with `exact_times=0` runs on a headway rather
than to a timetable, so `stop_times.txt` gives it no scheduled arrival or
departure at the stop and there is nothing for a delay to be measured against.
The clause's own remedy is `:141`'s second sentence, "Instead, `time` should be
provided to indicate arrival/departure predictions", which the verdict file
folds into this rule: a feed that drops `delay` and states `time` satisfies both
halves, so a second rule would report the same stop_time_update twice.

**Not E046.** E046 fires when a stop_time_update provides only `delay` and the
matched `stop_times.txt` row has no `arrival_time` or `departure_time` to add it
to, which is a question about the static feed's completeness. This rule says the
`delay` should not be there at all, on any stop of the trip, whatever
`stop_times.txt` holds. The two can coexist on one feed and neither implies the
other.

**Scope is `TripUpdate` alone**, because the sentence names
`TripUpdate.StopTimeUpdate`. `TripUpdate.delay` is a different field and a
different statement (`:62`), which the verdict file rejects under R3.

**Presence, not truthiness.** A stated `delay` of zero is a stated deviation
from a schedule that does not exist, so it is reported like any other.

`exact_times_zero_trip_ids` is `GtfsMetadata`'s own set, where a blank
`exact_times` cell reads as 0 because onebusaway types the column as a
primitive int. Nothing here re-derives it.

**Under a 2015 decode this fixture is fully visible.** `delay`,
`StopTimeEvent` and `frequencies.txt` all predate the current schema, so the
jar reads the message whole; what makes this rule new is that no validator in
the 56 asks this question, not that the fields are invisible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import relationships
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P013"

CLAUSE = (
    "In [TripUpdate.StopTimeUpdate](#stoptimeupdate), the [StopTimeEvent](#stoptimeevent) for "
    "`arrival` and `departure` should not contain `delay` because frequency-based trips do not "
    "follow a fixed schedule."
)

#: `StopTimeUpdate`'s two `StopTimeEvent` fields, in field-number order, which
#: is the order a pair of occurrences on one update reads in.
EVENTS = ("arrival", "departure")

FIELD = "delay"

FORBIDDEN = (
    "trip_id {trip_id} stop_time_update[{index}] {event} has {field} on an exact_times=0 trip"
)


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per event carrying `delay` on a frequency-based trip.

    The walk is `_shared/schedule_relationship.relationships`, which resolves
    relationships this rule does not read. It is here for the other half of what
    it carries: indexed stop_time_updates with their `entityPath`s, over
    TripUpdates only. `_shared/walk_stop_time_updates.py` is the alternative and
    is the wrong one, being `StopTimeUpdateValidator`'s stateful port with
    E051's `break` in it.
    """
    frequency_trips = ctx.static.exact_times_zero_trip_ids
    return [
        found
        for record in relationships(message, ctx)
        if record.payload == "trip_update" and record.trip.get("trip_id") in frequency_trips
        for found in _of_trip(record)
    ]


def _of_trip(record: TripRelationship) -> list[Occurrence]:
    trip_id = record.trip.get("trip_id")
    return [
        Occurrence(
            RULE_ID,
            FORBIDDEN.format(trip_id=trip_id, index=stop_time.index, event=event, field=FIELD),
            {
                ENTITY_PATH_KEY: f"{stop_time.path}.{event}",
                "tripId": trip_id,
                "field": FIELD,
            },
        )
        for stop_time in record.stop_time_updates
        for event in EVENTS
        if stop_time.update.has(event) and stop_time.update.get(event).has(FIELD)
    ]
