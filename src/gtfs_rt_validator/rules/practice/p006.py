"""P006: a trip cancelled over several days with no NO_SERVICE Alert naming it.

`:50`. Cancelling a trip for a week tells a consumer's trip planner to stop
offering it, and tells a rider nothing: the TripUpdates say the trip is gone,
and only the Alert says why and for how long. The clause asks for both halves,
so this rule reports the feed that has the first half and not the second.

**The Alert half is asked of the whole cycle, not of this message.** An agency
that publishes `-tu` and `-sa` separately satisfies the clause across two files
of one run, so a rule that looked only in the message it was handed would report
every correctly alerted cancellation in a real deployment.
`_shared/alert_index.visible_index` is that read, and P015 shares it.

**It reads the cycle from every role, and hosting is not its question.** The
scope of the Alert half is `ctx.cycle`, which `runner/context.py` puts on every
role's context; `ctx.combined`, which only the host gets, answers "am I the one
who reports?" and belongs to the cross-feed rules that emit one finding per
cycle. This rule is not one of them: it reports against the message it was
handed, one occurrence per trip in that message, so running it on three roles of
a cycle produces three answers about three files rather than one answer three
times. Reading the cycle costs it nothing and buys it the Alerts file.

**With no cycle at all it falls back to its own message, and that is a complete
answer rather than a partial one.** A context carrying no cycle is one message
standing alone, so every Alert that exists is in it. That is the case this rule
used to conflate with not hosting a cycle, which is a different thing entirely:
"I was not shown the Alerts" was true of a non-host message and is now true of
nothing, because every role is shown them. P015 answers both cases the same way,
because reading a cycle and reporting for one are two questions and only
`ctx.combined` answers the second.

**The TripUpdates half is read from the message being validated**, which under
the paragraph above is the TripUpdates feed's own message. Reading them from the
cycle as well would let a trip's days be assembled from two roles' files, a
shape no supported role layout produces, at the price of an occurrence whose
`entityPath` points into a file other than the one it is reported against.

**What "cancelling over a number of days" is taken to mean.** Group the
message's TripUpdates by `trip_id`; the days are the distinct `start_date`
values among them. The rule fires when there are two or more days and **every**
one of those TripUpdates is CANCELED. Two consequences, both deliberate:

* A trip that runs on one day and is cancelled on another is silent. The clause
  describes a producer cancelling a run of days, and a mixed feed is a trip
  whose service changed rather than one withdrawn over a period. This is the
  narrower reading of the two available, and the narrower one is right where a
  false positive would be telling a correct producer to publish an Alert about
  service it is still running.
* A TripUpdate naming no `start_date` names no day. It is neither counted nor
  able to break the cancellation, because the sentence counts `start_dates` and
  this TripUpdate has none.

Two or more TripUpdates naming the *same* day count once: the days are distinct
values, and a repeated instance is S003's finding rather than a second day.

**The relationship is the effective one**, resolved by
`_shared/schedule_relationship.py`, so a descriptor that declares nothing reads
as SCHEDULED and takes its trip out of scope.

**No overlap with the 56.** Nothing upstream reads `Alert.effect` except
`VehicleValidator`'s DETOUR scan (E029), nothing upstream groups TripUpdates by
trip across `start_date`s, and no upstream rule spans two feed files unless one
message carries two entity types. `tests/test_practice_tier_does_not_shadow_the_jar.py`
records what the jar said over this rule's fixture rather than predicting it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.alert_index import visible_index
from gtfs_rt_validator.rules._shared.schedule_relationship import CANCELED, relationships
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P006"

CLAUSE = (
    "When canceling trips over a number of days, producers should provide TripUpdates "
    "referencing the given `trip_ids` and `start_dates` as `CANCELED` as well as an Alert with "
    "`NO_SERVICE` referencing the same `trip_ids` and `TimeRange` that can be shown to riders "
    "explaining the cancellation (e.g., detour)."
)

#: `Alert.Effect.NO_SERVICE`. The number is 1 under the 2015 schema and under
#: the current one alike, so reading it here needs no schema and is therefore
#: not a mode branch; `tests/test_rule_p006.py` asserts that stays true. The
#: same arrangement `_shared/vehicle_bounds.DETOUR_EFFECT` has, for the same
#: reason.
NO_SERVICE_EFFECT = 1

#: The effect's name, for the occurrence text. Spelled beside the number so the
#: two cannot drift into naming different members.
NO_SERVICE = "NO_SERVICE"

UNALERTED = (
    "trip_id {trip_id} is {canceled} on {count} start_dates ({dates}) and no Alert in this "
    "feed cycle names it with effect {effect}"
)


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per multi-day cancellation the cycle's Alerts do not cover.

    In the order the trips first appear in this message, on every role, because
    the Alerts are read from the cycle rather than from whichever message hosts
    it. With no cycle the message is the whole scope; the module docstring says
    why that is not the same as not hosting one.
    """
    alerts = visible_index(message, ctx)
    return [
        _found(trip_id, records)
        for trip_id, records in _by_trip(message, ctx).items()
        if _cancelled_over_days(records)
        and NO_SERVICE_EFFECT not in alerts.effects_for_trip(trip_id)
    ]


def _by_trip(message: Msg, ctx: RuleContext) -> dict[str, list[TripRelationship]]:
    """This message's dated TripUpdates, grouped by the trip they name.

    A descriptor with no `trip_id` names no trip and one with no `start_date`
    names no day, so neither is grouped with anything.
    """
    grouped: dict[str, list[TripRelationship]] = {}
    for record in relationships(message, ctx):
        trip = record.trip
        if record.payload == "trip_update" and trip.has("trip_id") and trip.has("start_date"):
            grouped.setdefault(trip.get("trip_id"), []).append(record)
    return grouped


def _cancelled_over_days(records: list[TripRelationship]) -> bool:
    """Two or more distinct `start_date`s, every one of them CANCELED."""
    return len(_days(records)) > 1 and all(record.relationship == CANCELED for record in records)


def _days(records: list[TripRelationship]) -> list[str]:
    """The distinct `start_date` values, in the order the message states them."""
    return list(dict.fromkeys(record.trip.get("start_date") for record in records))


def _found(trip_id: str, records: list[TripRelationship]) -> Occurrence:
    days = _days(records)
    return Occurrence(
        RULE_ID,
        UNALERTED.format(
            trip_id=trip_id,
            canceled=CANCELED,
            count=len(days),
            dates=", ".join(days),
            effect=NO_SERVICE,
        ),
        {
            ENTITY_PATH_KEY: records[0].path.removesuffix(".trip"),
            "tripId": trip_id,
            "startDates": days,
            "entityIndexes": [record.entity_index for record in records],
        },
    )
