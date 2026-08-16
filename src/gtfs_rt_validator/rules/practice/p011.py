"""P011: an Alert naming an exact_times=1 trip whose start_time is off the headway.

`:126`. An `exact_times=1` `frequencies.txt` period declares departures at
`start_time`, `start_time + headway_secs`, and so on; a realtime `start_time`
that is none of those names a trip run that the static feed does not describe,
so a consumer cannot join the two.

**The predicate is E019's, at a third site.** `rules/upstream/e019.py:check`
reads `entity.has("trip_update")` and `entity.has("vehicle")` and nothing else,
so an `Alert.informed_entity[].trip` carrying a `trip_id` and a `start_time` is
checked by nothing in the 56. The stepping is not copied: both rules read
`_shared/frequencies.start_times`, which is upstream's own
`for (int t = start; t < end; t += headway)` written once.

**Three deliberate divergences from E019, and the point of naming them here is
that a reader comparing the two files should not "fix" either to match the
other.** E019 is a byte contract against the jar and P011 has no jar to match.

1. **The candidate rendering.** `e019.vehicle_position_clock` reproduces `:105`'s
   inlined `String.format("%02d:%02d:%02d", t / 3600, t % 360, t % 60)`, whose
   middle field is `% 360` where it should be `(t / 60) % 60`. It renders a
   period starting at 06:01:00 as `06:60:00`. P011 renders with
   `_shared/times.seconds_after_midnight_to_clock`, the correct function, which
   E019's TripUpdate branch also uses.
2. **What the occurrence names.** `e019._search` reads `gtfsStartTimeString` and
   `headwaySecs` after the loop, so a failing comparison reports whichever
   candidate the final iteration of the final period happened to leave behind.
   P011 reports each period's own declared `start_time` and `headway_secs`, all
   of them, so a two-period trip says what both periods were.
3. **The guard on `start_time`.** E019 reads `getStartTime()` unguarded (point 4
   of its docstring), so a descriptor stating no start_time compares `""`
   against every candidate and always reports. The clause's own antecedent here
   is "when `trip_id` and `start_time` are within `exact_time=1` interval", so a
   selector naming no start_time is outside it and P011 is silent. The plan
   names the first two divergences and not this one; it is the same family and
   it is recorded rather than assumed.

**Under a 2015 decode the fixture is fully visible.** `Alert`,
`EntitySelector.trip`, `trip_id` and `start_time` are all 2015 fields, so the
jar reads this message whole and still reports nothing, because it has no Alert
branch to report from.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.frequencies import Row, headway_secs, start_time, start_times
from gtfs_rt_validator.rules._shared.schedule_relationship import relationships
from gtfs_rt_validator.rules._shared.times import seconds_after_midnight_to_clock
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P011"

CLAUSE = (
    "When `trip_id` and `start_time` are within `exact_time=1` interval, `start_time` should "
    "be later than the beginning of the interval by an exact multiple of `headway_secs`."
)

OFF_HEADWAY = (
    "trip_id {trip_id} start_time {start_time} is not an exact multiple of headway_secs "
    "after the start of any exact_times=1 period; frequencies.txt declares {declared}"
)

DECLARED = "{start_time} every {headway} seconds"


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per `informed_entity` selector that matches no candidate.

    The walk is `_shared/schedule_relationship.relationships`, which is the only
    shared walk reaching all three `TripDescriptor` sites and the only one that
    knows a selector's index. This rule reads none of the relationships it
    resolves; it wants the descriptor and the path.
    """
    periods = ctx.static.exact_times_one_trips
    return [
        _found(record, listed)
        for record in relationships(message, ctx)
        if record.payload == "alert" and record.trip.has("start_time")
        for listed in [periods.get(record.trip.get("trip_id"))]
        if listed is not None and not _matches(listed, record.trip.get("start_time"))
    ]


def _matches(periods: Iterable[Row], wanted: str) -> bool:
    """Whether `wanted` is one of the departures the periods declare.

    Rendered rather than parsed: the wire carries `start_time` as a clock string
    and nothing in this project parses one back to seconds after midnight, so
    the comparison happens in the direction that needs no new parser. The
    rendering is the correct one; see divergence 1 in the module docstring.
    """
    return any(
        seconds_after_midnight_to_clock(candidate) == wanted
        for period in periods
        for candidate in start_times(period)
    )


def _declared(periods: Sequence[Row]) -> str:
    """Every period the static feed declares for the trip, in table order."""
    return ", ".join(
        DECLARED.format(
            start_time=seconds_after_midnight_to_clock(start_time(period)),
            headway=headway_secs(period),
        )
        for period in periods
    )


def _found(record: TripRelationship, periods: Sequence[Row]) -> Occurrence:
    trip_id = record.trip.get("trip_id")
    wanted = record.trip.get("start_time")
    return Occurrence(
        RULE_ID,
        OFF_HEADWAY.format(trip_id=trip_id, start_time=wanted, declared=_declared(periods)),
        {ENTITY_PATH_KEY: record.path, "tripId": trip_id, "startTime": wanted},
    )
