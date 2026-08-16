"""P008: a live TripUpdate that predicts no arrival or departure in the future.

`:60`. A TripUpdate whose every prediction is already in the past tells a
consumer nothing it can show a rider: the trip is being published as if it were
running, and every time on it has been overtaken by the clock.

**This rule narrows its statement, and the narrowing is the thing to read
first.** "While the trip is in progress" is the sentence's antecedent, and no
field of a GTFS-Realtime feed states that a trip is in progress. The proxy is
the condition under which a producer is asserting live predictions: the
TripUpdate exists, its trip is neither CANCELED nor DELETED, it carries at least
one stop_time_update, and not every one of those is SKIPPED.

**The known false-positive shape, named here rather than found by a user:** a
trip that has genuinely finished and whose TripUpdate is still being published
will be reported. Every prediction on it is in the past because the journey is
over, which is exactly the shape of the violation. The alternative proxy, taking
`VehiclePosition.current_stop_sequence` from another role's message, makes a run
over a TripUpdates feed alone report nothing at all, which is worse.
`upstream/practice-clause-verdicts.json` carries this as `rule_in_part` on
`60#1` with the same note.

**A trip whose every stop_time_update is SKIPPED is not in progress either**,
and it is exempt for the same reason a CANCELED one is: it will call at no
stop, so no journey is under way for a prediction to be about. That is the
third conjunct of the proxy, and it was added after measurement rather than by
reasoning. Over six recorded MBTA TripUpdates messages this rule produced 685
occurrences on 132 trips; P007 produced 618 on the same 103 trips every round,
and **618 of the 685, 90.2 percent, were trips P007 had already reported**. The
mechanism is mechanical rather than particular to that agency: an all-SKIPPED
trip carries no `time` and no `delay` anywhere, so it cannot carry a prediction,
so this rule reported it necessarily. That shape is `:51`'s finding, and
reporting it a second time under a second citation helps nobody. `:246` makes a
SKIPPED stop's times optional rather than forbidden, so the exemption reads the
relationships and not the absence of times.

The remaining 9 to 18 occurrences per message, 1.1 to 2.3 percent of the feed's
TripUpdates, are the finished-trip false positive above. **That settles whether
the proxy needs a fourth conjunct, in the negative:** the false positive is not
common, and a `VehiclePosition.current_stop_sequence` guard would address at most 2
percent of the firing at the price of a cross-role dependency this rule does not
have. The shape is shallow as well, a median 38 seconds past the last
prediction, with one trip over five minutes.

**"At least one stop_time_update" is a conjunct of the rule, not a shortcut.**
It is half the proxy above, and it is also what keeps this disjoint from E041:
`_shared/stop_time_update_checks.check_e041` already reports a TripUpdate with
no stop_time_updates that is not CANCELED. E041 asks whether there are any
updates; this asks whether any of them is still a prediction.

**"In the future" is strict and is measured against the run's clock**, which
`runner/clock.py` takes from the file rather than from the wall so an archive
replay is reproducible. A prediction for the clock's own second is not in the
future. Only `time` counts: a `StopTimeEvent` carrying `delay` alone states no
predicted arrival time, and the sentence asks for one.

**Under a 2015 decode the violation is fully visible**: `stop_time_update` and
`StopTimeEvent.time` both predate the current schema, so the jar reads the
message whole and simply has no rule that asks this. `DELETED = 7` is post-2015,
so that exemption is not expressible there: such a trip decodes as SCHEDULED.
`SKIPPED = 1` is in the 2015 stop_time_update enum, so the all-SKIPPED exemption
would be, which is the same asymmetry P007's docstring records from its side.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import (
    CANCELED,
    DELETED,
    SKIPPED,
    relationships,
)
from gtfs_rt_validator.rules._shared.times import age_millis
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P008"

CLAUSE = (
    "While the trip is in progress, all `TripUpdates` should include at least one "
    "`stop_time_update` with a predicted arrival or departure time in the future."
)

#: The two relationships under which a producer is asserting nothing about a
#: journey, so the antecedent cannot hold. DELETED is post-2015.
EXEMPT = (CANCELED, DELETED)

#: `StopTimeUpdate`'s two `StopTimeEvent` fields, in field-number order.
EVENTS = ("arrival", "departure")

#: The field a prediction is stated in. `delay` is not one: it states a
#: deviation, not a time.
TIME = "time"

NO_PREDICTION = (
    "trip_id {trip_id} has {count} stop_time_updates and none of them predicts "
    "an arrival or departure after {clock}"
)

_MILLIS_PER_SECOND = 1000


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per live TripUpdate with nothing left to predict.

    The walk is `_shared/schedule_relationship.relationships`, for the trip
    relationship and for the indexed stop_time_updates it carries alongside it.
    `_shared/walk_stop_time_updates.py` would be the wrong reuse: it is
    `StopTimeUpdateValidator`'s stateful port and carries E051's `break`, so a
    rule that has to see every update cannot read it.
    """
    now_millis = ctx.clock.millis
    return [
        _found(record, now_millis)
        for record in relationships(message, ctx)
        if record.payload == "trip_update"
        and record.relationship not in EXEMPT
        and record.stop_time_updates
        and not _calls_at_no_stop(record)
        and not any(_predicts_ahead(stop.update, now_millis) for stop in record.stop_time_updates)
    ]


def _calls_at_no_stop(record: TripRelationship) -> bool:
    """Is every stop of this trip one the vehicle will not stop at?

    P007 is the rule for that trip, and the docstring above has the measurement
    that made the overlap worth removing. Read off the resolved relationships,
    so an update that declares nothing counts as SCHEDULED and takes the trip
    out of the exemption, which is the same resolution P007 applies.
    """
    return all(stop.relationship == SKIPPED for stop in record.stop_time_updates)


def _predicts_ahead(update: Msg, now_millis: int) -> bool:
    """Does either event of this stop_time_update state a time after the clock?

    `age_millis` is negative for a time ahead of the clock, which is the same
    comparison `_shared/times.is_in_future` makes at a tolerance of zero without
    that helper's truncation to whole seconds.
    """
    return any(
        update.has(event)
        and update.get(event).has(TIME)
        and age_millis(now_millis, update.get(event).get(TIME)) < 0
        for event in EVENTS
    )


def _found(record: TripRelationship, now_millis: int) -> Occurrence:
    trip_id = record.trip.get("trip_id")
    count = len(record.stop_time_updates)
    return Occurrence(
        RULE_ID,
        NO_PREDICTION.format(trip_id=trip_id, count=count, clock=now_millis // _MILLIS_PER_SECOND),
        {
            ENTITY_PATH_KEY: record.path.removesuffix(".trip"),
            "tripId": trip_id,
            "stopTimeUpdateCount": count,
        },
    )
