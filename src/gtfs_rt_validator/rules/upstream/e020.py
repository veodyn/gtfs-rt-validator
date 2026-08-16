"""E020: a start_time that is not HH:MM:SS or H:MM:SS.

`checkE020` in `validation/rules/TripDescriptorValidator.java:273-278`, called
only under `trip.hasStartTime()` (`:118` and `:167`).

**Not enum-sensitive.** The gates read `hasStartTime()` alone and the body reads
`start_time` alone, so no schedule_relationship, recognised or not, can reach
it. An earlier draft named E020 alongside E003 and E016 as enum-sensitive; it is
not, in either direction.

The grammar is `_shared/timeformats.is_valid_time_format`: a length gate of
seven or eight characters, then `[0-2]?[0-9]:[0-5][0-9]:[0-5][0-9]`. The gate is
the whole trick, since the optional leading digit would otherwise also match
`1:2:3`. It makes `5:15:35` legal and `05:5:35` illegal, and hours run to 29
because service continues into the next service day, so `30:00:00` is refused.

The prefix is `getVehicleAndTripIdText(entity) + " start_time is " + startTime`,
and the offending string is echoed into it verbatim.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.walk_trip_descriptor import trip_descriptors
from gtfs_rt_validator.rules._shared.walks import events_for
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "E020"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
