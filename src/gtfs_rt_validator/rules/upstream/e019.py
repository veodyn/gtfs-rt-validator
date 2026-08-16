"""E019: an exact_times = 1 start_time that is not a multiple of headway_secs later.

Ported from `validation/rules/FrequencyTypeOneValidator.java:49-130` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. Two structurally identical branches,
TripUpdate (`:50-88`) then VehiclePosition (`:90-129`), each of which walks every
period of the trip, steps `start_time` by `headway_secs` until it reaches
`end_time`, and reports once if the realtime `start_time` matched no candidate.

Four things the Java does that a reasonable implementation would not, all
reproduced, and all four confirmed by running the pinned jar rather than by
reading the source alone.

**1. The VehiclePosition branch computes the wrong minutes.** `:105` inlines

```java
String.format("%02d:%02d:%02d", startTime / 3600, startTime % 360, startTime % 60)
```

where `:64` calls `TimestampUtils.secondsAfterMidnightToClock`, whose middle
field is `(startTime / 60) % 60`. The two agree exactly when `startTime` is a
multiple of 360 seconds, which every candidate in upstream's own test is, so its
test cannot see it. Against a period starting at 06:01:00 the jar reported
`09:60:00` from this branch and nothing at all from the other. Not a typo to
fix: under `--compat` upstream wins, and the modern reading of this rule would
have to be a separately cited rule rather than a branch here.

**2. The prefix names the last candidate tried, not the period's start_time.**
`gtfsStartTimeString` is assigned inside the `while` and read after it, so a
failing comparison reports whatever the final iteration of the final period left
behind. Measured: with testagency.zip's two periods for trip `15.1` the jar
reported `18:00:00`, and with a single 06:00:00 to 10:00:01 period it reported
`10:00:00`.

**3. Both locals stay `null` when no period ever starts.** A period whose
`start_time` is not before its `end_time` never enters the loop, so Java
concatenates two nulls: `start_time is null with a headway of null seconds `.
Hence `javafmt.java_str`, which renders `None` as `null`.

**4. Neither branch guards anything.** `getTripId()` and `getStartTime()` are
read straight off the descriptor, so a TripUpdate with no start_time compares
`""` against every candidate, matches none, and reports with a double space
where the value would have been. The VehiclePosition branch reads `getTrip()`
unguarded at `:94` too, and only checks `hasTrip()` inside the comparison at
`:109`, which is why a VehiclePosition with no trip can never match and would
report if the empty string were ever a key in the map.

Note the **trailing space** after `seconds` in the prefix, which is in the Java
literal and reaches the JSON.

A `headway_secs` of zero never advances the loop and the jar spins on it
forever. `rules/_shared/frequencies.py` owns that, and `runner/gate.py` owns
what this project does about it; nothing here treats it as a finding, because
upstream emits no occurrence for it either.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.frequencies import Row, headway_secs, start_times
from gtfs_rt_validator.rules._shared.javafmt import java_str
from gtfs_rt_validator.rules._shared.times import seconds_after_midnight_to_clock
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "E019"


def vehicle_position_clock(seconds_after_midnight: int) -> str:
    """`:105`'s inlined format, `% 360` and all. See point 1 of the docstring.

    Every value it is handed comes from `frequencies.txt` stepped forward by a
    positive headway, so it is non-negative and Java's truncating division and
    Python's flooring one agree; `_shared/times.py` carries the signed case for
    `secondsAfterMidnightToClock`, which E023 does reach with a negative.
    """
    hours = seconds_after_midnight // 3600
    minutes = seconds_after_midnight % 360
    seconds = seconds_after_midnight % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """The TripUpdate branch then the VehiclePosition branch, per entity."""
    periods = ctx.static.exact_times_one_trips
    for entity in message.get("entity"):
        if entity.has("trip_update"):
            trip = entity.get("trip_update").get("trip")
            clock = seconds_after_midnight_to_clock
            yield from _branch(trip, periods, clock, trip.get("start_time"))
        if entity.has("vehicle"):
            position = entity.get("vehicle")
            trip = position.get("trip")
            # `:109`'s `vehiclePosition.hasTrip() &&`: a position with no trip
            # walks every candidate and matches none, rather than skipping.
            wanted = trip.get("start_time") if position.has("trip") else None
            yield from _branch(trip, periods, vehicle_position_clock, wanted)


def _branch(
    trip: Msg,
    periods: Mapping[str, list[Row]],
    clock: Callable[[int], str],
    wanted: str | None,
) -> Iterator[Occurrence]:
    """One branch of the Java: at most one occurrence, and none for an unlisted trip.

    `periods.get(tripId) is None` is `getExactTimesOneTrips().get(tripId) !=
    null`, the only gate either branch has.
    """
    listed = periods.get(trip.get("trip_id"))
    if listed is None:
        return
    matched, last, headway = _search(listed, clock, wanted)
    if matched:
        return
    yield Occurrence(
        RULE_ID,
        f"GTFS-rt trip_id {trip.get('trip_id')} has start_time of {trip.get('start_time')} "
        f"and GTFS frequencies.txt start_time is {java_str(last)} "
        f"with a headway of {java_str(headway)} seconds ",
    )


def _search(
    periods: Iterable[Row], clock: Callable[[int], str], wanted: str | None
) -> tuple[bool, str | None, int | None]:
    """`foundMatch`, `gtfsStartTimeString` and `headwaySecs` after the nested loop.

    The last two are `None` until the inner body runs for the first time, which
    is what puts the word `null` in the occurrence, and afterwards they hold the
    last value any period assigned, which is what puts the last candidate there
    rather than the nearest one.
    """
    last: str | None = None
    headway: int | None = None
    for period in periods:
        for candidate in start_times(period):
            last = clock(candidate)
            headway = headway_secs(period)
            if wanted is not None and wanted == last:
                return True, last, headway
    return False, last, headway
