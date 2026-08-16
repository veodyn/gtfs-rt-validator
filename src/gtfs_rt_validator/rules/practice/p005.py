"""P005: a VehiclePosition timestamp more than 90 seconds behind the run's clock.

The document's own worked example, and the one rule in the tier that declares no
upstream overlap and has that confirmed by the jar rather than only by reading
the Java. Measured, one invocation per case over the pinned jar:

| entity age, seconds | jar |
|---|---|
| 0 | nothing |
| 90 | nothing |
| 91 | nothing |
| 100 | nothing |
| the entity timestamp ahead of the header | E012 |

W008 is the header against the clock, E012 is the entity against the header and
E050 is the future. Nothing in the 56 compares an entity timestamp against the
clock at any age, which is exactly the hole the cited sentence exists to name: a
producer refreshing `FeedHeader.timestamp` every 30 seconds keeps W008 quiet
while every VehiclePosition inside it goes stale.

**The clock is the run's, not the wall's.** `runner/clock.py` reads it from the
file's modification time or its name, the way `BatchProcessor.java:220-232`
does, which is what makes an archive replay reproducible.

**The 90 is exclusive.** "should not be older than 90 seconds" is satisfied by
exactly 90, so the boundary is silent and 91 is the first age reported.

**Gated on the POSIX window, and that is this rule's decision rather than the
cited sentence's.**
Upstream's entity ladder reports a non-POSIX timestamp as E001 and stops
(`walk_timestamp._entity_timestamp_events`), so a timestamp of 100 is already
somebody's finding and is not a time at all. Without this gate P005 would fire
beside E001 on every such value, which is an overlap this rule does not declare.
With it, a nonsense timestamp is E001's and a plausible but stale one is this
rule's.

**VehiclePositions only.** The sentence names them, and `:61`'s
`TripUpdate.timestamp` sentence is rejected under R3, so nothing here reads one.

An absent timestamp is W001's: upstream reads the field with no `has` test, so
zero and absent are the same thing to it and to this rule.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.ids import vehicle_and_trip_id_text
from gtfs_rt_validator.rules._shared.times import age_millis, is_posix
from gtfs_rt_validator.rules._shared.timestamp_pass import at
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P005"

CLAUSE = (
    "For example, even if a producer is continuously refreshing the `FeedHeader.timestamp` "
    "timestamp every 30 seconds, the age of VehiclePositions within that feed should not be "
    "older than 90 seconds."
)

#: The document's number, in seconds, and the comparison against it is strict.
MAX_AGE_SECONDS = 90

_MILLIS_PER_SECOND = 1000

REPORTED = (
    "{who} timestamp {timestamp} is {age} seconds old, "
    f"more than the {MAX_AGE_SECONDS} seconds the practice allows"
)


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per stale VehiclePosition, in feed order."""
    return [
        found
        for index, entity in enumerate(message.get("entity"))
        if entity.has("vehicle")
        for found in _of_vehicle(entity.get("vehicle"), index, ctx.clock.millis)
    ]


def _of_vehicle(position: Msg, index: int, now_millis: int) -> list[Occurrence]:
    timestamp = position.get("timestamp")
    if timestamp == 0 or not is_posix(timestamp):
        return []
    age = age_millis(now_millis, timestamp) // _MILLIS_PER_SECOND
    if age <= MAX_AGE_SECONDS:
        return []
    return [
        Occurrence(
            RULE_ID,
            REPORTED.format(who=vehicle_and_trip_id_text(position), timestamp=timestamp, age=age),
            {
                **at(f"entity[{index}].vehicle"),
                "ageSeconds": age,
                "timestamp": timestamp,
            },
        )
    ]
