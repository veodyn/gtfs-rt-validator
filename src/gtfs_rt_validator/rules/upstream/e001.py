"""E001: a time that is not inside the POSIX window upstream accepts.

**Seven emission sites**, more than any other rule in
`TimestampValidator`, all reached from `rules/_shared/walk_timestamp.py`: the
header (`:104`), a TripUpdate's timestamp (`:156`), a stop_time_update's arrival
(`:191`) and departure (`:224`), a VehiclePosition's timestamp (`:283`), and an
alert active_period's start (`:351`) and end (`:356`).

`TimestampUtils.isPosix` is a window and not a shape test: 1104537600 to
1991620134 inclusive, Jan 2005 to Feb 2033. The error it exists to catch is a
producer publishing milliseconds where seconds were meant, which lands far above
the ceiling.

Three details of the sites, each of which changes what is reported:

- The entity sites are inside the `else` of `timestamp == 0`, so an absent
  timestamp is W001 and never E001.
- The stop_time_update sites are guarded by `hasArrival() && arrival.hasTime()`,
  so a `StopTimeEvent` carrying only a delay is not checked.
- The alert sites are guarded by `hasStart()` / `hasEnd()`, so an absent bound
  is not reported as the 0 it would otherwise decode to.

E012 is emitted before E001 for the same entity timestamp (`:150-156`), so a
value that is both past the header and outside the window reports under both
ids. The stop_time_update prefixes use the loop's own `stopDescription`, which
carries a leading space and is not `GtfsUtils.getStopTimeUpdateId`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.walk_timestamp import timestamps
from gtfs_rt_validator.rules._shared.walks import events_for
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "E001"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Every E001 the shared walk saw, header first and then entity order."""
    for event in events_for(RULE_ID, timestamps, message, ctx):
        yield Occurrence(RULE_ID, event.prefix, event.context)
