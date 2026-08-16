"""S007: an `exact_times=0` trip whose stop_time_updates are SCHEDULED.

`:242`, inside the `SCHEDULED` member's own comment, and a WARNING because the
sentence says `should`.

**Not E013, and the difference is why this id exists.** E013 reads the *trip's*
schedule_relationship and accepts "UNSCHEDULED or empty" for an `exact_times=0`
trip. That was correct in 2015, when `StopTimeUpdate.ScheduleRelationship` had
three members and no UNSCHEDULED. The pinned proto adds `UNSCHEDULED = 3` to
that enum and puts this sentence in SCHEDULED's comment, so the value it forbids
is the one the *stop_time_updates* carry. E013 never looks at one. So nothing
about E013 changes: the fix for an upstream rule too lenient for the current
source is a new id, never a branch in the old one, which is also what
`tests/test_no_mode_branch.py` enforces structurally.

**The resolved value, not the declared one.** An absent `schedule_relationship`
is SCHEDULED to every consumer, so a producer that omitted it has still given
the update a SCHEDULED value. `_shared/schedule_relationship.py` carries both
readings and this rule wants the first.

`exact_times_zero_trip_ids` is the set `GtfsMetadata` builds, where a blank
`exact_times` cell reads as 0, which is the same "empty or equal to 0" the
DUPLICATED comment spells out at `:879`.

## One occurrence per trip, because the sentence's subject is the trip

The clause reads "Frequency-based **trips** ... should not have a SCHEDULED
value and should use UNSCHEDULED instead". The bearer of the obligation is the
trip, and the two sentences immediately before it in the same comment say "this
update" when they mean one stop_time_update: `240#1` "At least one of arrival
and departure must be provided", E043's, and `240#2` "then so must this update",
S006's, which ends on `:242` where this sentence begins. The subject changes
between one sentence and the next in the same line, and it changes to the plural
noun this rule is scoped by. `:859`, S010's clause, is what a distributive
reading looks like when the proto wants one: "must also set **all**
StopTimeUpdates". This sentence says no such thing, and "a SCHEDULED value" is
singular.

So this counts the way S009 counts and for the reason S009 gives: the defect the
sentence names belongs to the trip, so a trip with 95 SCHEDULED updates is one
frequency-based trip carrying a SCHEDULED value rather than 95 defects. The
occurrence names the trip and its `entityPath` is the descriptor's, because an
occurrence pointing at one arbitrary stop of 95 points a reader at the wrong
thing. How many of the trip's updates were SCHEDULED is in the text, so nothing
a per-update count carried is lost.

**Per descriptor, which is not the same as per trip_id per message.** A
frequency-based trip is exactly the kind that runs several times at once, and
the recorded feed sends one TripUpdate per run, told apart by `start_time`, all
sharing a trip_id. Each is a descriptor of its own carrying the value the clause
forbids, and the walk hands this rule one record for each, so each is reported.
Collapsing them on trip_id would report on the feed's entity list rather than on
the clause, and would hide a producer that fixed one run and not its neighbour.

**Measured, on the one recorded agency whose `frequencies.txt` has rows.** Over
six Clovis Transit messages (`mdb-2894`, 30 entities each) the per-update
reading produced **4531 occurrences over 8 distinct trips**, a ratio of 566 to
1, and out-reported every other spec rule on that agency by two orders of
magnitude. The producer declares `schedule_relationship` nowhere, at either
level, so all 4531 were the proto2 default resolved as SCHEDULED rather than a
producer having said it. Per trip the count is **180**, and the arithmetic is
worth stating because it is not 48: each message carries 30 TripUpdates over
those 8 trip_ids, being 16 distinct `(trip_id, start_time)` runs of which some
are sent two and three times over, so 30 descriptors per message across six
messages. Still 25 times fewer occurrences, saying the same thing about the same
8 trips.

This is not a narrowing of the clause and its verdict stays `rule`: every
frequency-based trip carrying a SCHEDULED value is still reported, and the set
of subjects the rule names is unchanged. Only the number of times each is named
moved.

**The per-update naming already has an owner.** Once a producer sets the
descriptor to UNSCHEDULED and leaves an update SCHEDULED, S010 fires on `:859`
and names each such update, which is the state where naming them is what the
producer needs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import (
    STOP_TIME_SCHEDULED,
    relationships,
)
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S007"

CLAUSE = (
    "Frequency-based trips (GTFS frequencies.txt with exact_times = 0) should not have a "
    "SCHEDULED value and should use UNSCHEDULED instead."
)

SCHEDULED_ON_FREQUENCY = (
    "trip_id {trip_id} has {count} of {total} stop_time_updates SCHEDULED on an exact_times=0 trip"
)


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per frequency-based trip carrying a SCHEDULED value."""
    frequency_trips = ctx.static.exact_times_zero_trip_ids
    return [
        found
        for record in relationships(message, ctx)
        if record.payload == "trip_update" and record.trip.get("trip_id") in frequency_trips
        for found in _of_trip(record)
    ]


def _of_trip(record: TripRelationship) -> list[Occurrence]:
    """The trip's one occurrence, or none if no update of it resolved SCHEDULED.

    A trip with no stop_time_updates at all has no SCHEDULED value to object to
    and is E041's, not this rule's.
    """
    scheduled = sum(
        stop_time.relationship == STOP_TIME_SCHEDULED for stop_time in record.stop_time_updates
    )
    if not scheduled:
        return []
    trip_id = record.trip.get("trip_id")
    return [
        Occurrence(
            RULE_ID,
            SCHEDULED_ON_FREQUENCY.format(
                trip_id=trip_id, count=scheduled, total=len(record.stop_time_updates)
            ),
            {ENTITY_PATH_KEY: record.path, "tripId": trip_id, "scheduled": scheduled},
        )
    ]
