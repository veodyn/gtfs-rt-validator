"""P007: a trip whose every stop_time_update is SKIPPED and that is not cancelled.

`:51`. Skipping every stop of a trip and cancelling it describe the same
service, and a consumer told the first has to infer the second: it sees a trip
that is still running, stop by stop, with nowhere to stop. The clause names the
remedy, so the finding is "say CANCELED instead" rather than "something is
wrong".

**At least one stop_time_update is part of the test, not an implementation
detail.** A TripUpdate carrying none vacuously has all zero of them SKIPPED, and
firing there would report `_shared/stop_time_update_checks.check_e041`'s finding
under a second id. The sentence presupposes some too: "having all
`stop_time_updates` being marked as `SKIPPED`".

**The exemption is the clause's own "unless" half**, and it is read this way:
the trip is silent when its effective relationship is CANCELED, NEW or
DUPLICATED. CANCELED is silent because it is the remedy the
sentence asks for. NEW and DUPLICATED are silent because a trip this feed
invented can be withdrawn by skipping every stop of it, which is what "was
subsequently canceled" describes. Nothing else is exempt; DELETED in particular
is P008's exemption and not this one's.

The relationship is the **effective** one, so a trip that declares nothing
resolves to SCHEDULED and is reported. `_shared/schedule_relationship.py` owns
that resolution and the member names, so no enum number is spelled here.

**Under a 2015 decode the exemption disappears.** `SKIPPED = 1` is in the 2015
stop_time_update enum, so the violation is fully visible to the jar, but `NEW =
8` and `DUPLICATED = 6` are not in the 2015 trip enum: the decoder drops the
field and both exempt trips read as SCHEDULED trips with every stop skipped.
The jar cannot tell an exempt trip from a reported one, which is one reason
this check is not expressible there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import (
    CANCELED,
    DUPLICATED,
    NEW,
    SKIPPED,
    relationships,
)
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P007"

CLAUSE = (
    "If no stops in a trip will be visited, the trip should be `CANCELED` instead of having all "
    "`stop_time_updates` being marked as `SKIPPED`, unless the trip was a `NEW` or `DUPLICATED` "
    "trip and was subsequently canceled."
)

#: The three the sentence exempts. CANCELED is the remedy it asks for; NEW and
#: DUPLICATED are its "unless" half, and both are post-2015 members.
EXEMPT = (CANCELED, NEW, DUPLICATED)

ALL_SKIPPED = (
    "trip_id {trip_id} has all {count} stop_time_updates {skipped} "
    "and is {relationship} rather than {canceled}"
)


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per fully skipped trip, in feed order.

    The walk is `_shared/schedule_relationship.relationships`, which resolves
    both enums at once and yields indexed stop_time_updates with their paths.
    `_shared/walk_stop_time_updates.py` is the wrong reuse for a modern rule:
    it is `StopTimeUpdateValidator`'s stateful port and carries E051's `break`,
    so it does not see every update.
    """
    return [
        _found(record)
        for record in relationships(message, ctx)
        if record.payload == "trip_update"
        and record.relationship not in EXEMPT
        and record.stop_time_updates
        and all(stop.relationship == SKIPPED for stop in record.stop_time_updates)
    ]


def _found(record: TripRelationship) -> Occurrence:
    trip_id = record.trip.get("trip_id")
    return Occurrence(
        RULE_ID,
        ALL_SKIPPED.format(
            trip_id=trip_id,
            count=len(record.stop_time_updates),
            skipped=SKIPPED,
            relationship=record.relationship,
            canceled=CANCELED,
        ),
        {
            ENTITY_PATH_KEY: record.path.removesuffix(".trip"),
            "tripId": trip_id,
            "scheduleRelationship": record.relationship,
        },
    )
