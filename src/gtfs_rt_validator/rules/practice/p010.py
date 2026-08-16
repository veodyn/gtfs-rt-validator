"""P010: a NEW or REPLACEMENT trip whose stop_time_updates state no scheduled_time.

`:106`, the recommendation row for `StopTimeUpdate.StopTimeEvent.scheduled_time`.
A NEW trip has no GTFS row to deviate from and a REPLACEMENT trip's schedule is
by definition not the one GTFS carries, so `scheduled_time` is the only thing
that says what the trip was *meant* to do. Without it a consumer has predictions
it cannot compare against anything, and cannot compute a delay at all.

**This rule asks for `scheduled_time` somewhere, not for all timepoints, and
that is a deliberate narrowing.** The clause ends "`scheduled_time` should be
provided for all timepoints". Which stops of a trip are timepoints comes from
`stop_times.timepoint`, an optional column, and reading it would make this the
only rule in either cited tier whose verdict depends on an optional column of an
already-loaded table behaving a particular way: a feed that omits the column
would have every stop read as a timepoint, and every partially scheduled trip
would be reported. "This NEW trip provides no scheduled times at all" is the
half that is worth reporting and never false-positives on a partially
timepointed trip. `upstream/practice-clause-verdicts.json` records `106#1` as
`rule_in_part` with that narrowing. The citation quotes the whole sentence
because the citation gate is verbatim.

**A trip carrying no `stop_time_update` at all is not this rule's finding.**
There is then nothing that could carry a `scheduled_time`, and the empty
TripUpdate is E041's subject; firing here would report every NEW stub under two
ids. The clause does not settle it either way, so the choice is recorded here
rather than left to be inferred from the code.

**The converse rule is S004**, which reports `scheduled_time` where the
proto forbids it: on a trip that is not NEW, REPLACEMENT or DUPLICATED. Its
exempt set is a superset of this rule's scope and it fires on presence where
this one fires on absence, so no stop_time_update can draw both.
`tests/test_rule_p010.py` walks the corners of that claim rather than stating
it.

**Under a 2015 decode there is nothing here at all.** `NEW = 8` and
`REPLACEMENT = 7` are not members of the 2015 `ScheduleRelationship` and
`scheduled_time` is a post-2015 field, so the jar sees a SCHEDULED trip whose
stop_time_updates carry unknown fields.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import NEW, REPLACEMENT, relationships
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P010"

CLAUSE = (
    "If the trip is a new or replacement trip, and the trip will run according to a schedule "
    "(which can be a modified schedule in case of a replacement trip), `scheduled_time` should "
    "be provided for all timepoints."
)

#: The two the sentence names. DUPLICATED is not among them: a duplicate copies
#: a trip GTFS already schedules, so its schedule is derivable.
IN_SCOPE = (NEW, REPLACEMENT)

#: `StopTimeUpdate`'s two `StopTimeEvent` fields, in field-number order.
EVENTS = ("arrival", "departure")

FIELD = "scheduled_time"

MISSING = "trip_id {trip_id} is {relationship} and no stop_time_update provides a {field}"


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per trip, never per stop: the finding is about the trip."""
    return [
        _found(record)
        for record in relationships(message, ctx)
        if record.payload == "trip_update"
        and record.relationship in IN_SCOPE
        and record.stop_time_updates
        and not _any_scheduled(record)
    ]


def _any_scheduled(record: TripRelationship) -> bool:
    """Whether one `scheduled_time` anywhere on the trip states its schedule."""
    return any(
        stop_time.update.has(event) and stop_time.update.get(event).has(FIELD)
        for stop_time in record.stop_time_updates
        for event in EVENTS
    )


def _found(record: TripRelationship) -> Occurrence:
    trip_id = record.trip.get("trip_id")
    return Occurrence(
        RULE_ID,
        MISSING.format(trip_id=trip_id, relationship=record.relationship, field=FIELD),
        {
            # The trip_update rather than the descriptor: the missing field
            # would have sat under the stop_time_updates, not under the trip.
            ENTITY_PATH_KEY: record.path.removesuffix(".trip"),
            "tripId": trip_id,
            "scheduleRelationship": record.relationship,
        },
    )
