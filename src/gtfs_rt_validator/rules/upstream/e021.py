"""E021: a start_date that is not YYYYMMDD.

`checkE021` in `validation/rules/TripDescriptorValidator.java:313-319`. The
dispatch calls it unconditionally on both vehicle-bearing sides (`:122` and
`:172`) because the `hasStartDate()` test is inside the helper rather than
around it.

**The resolver is SMART, not STRICT**, and this is the one place a reading of
`parseStrict()` as resolver strictness goes wrong. `TimestampUtils` builds its formatter with
`parseStrict()`, which sets *parse* strictness, while `toFormatter()` leaves the
resolver at its SMART default: the "previous valid day" branch. Measured on JDK
17.0.19, `20170230`, `20170229` in a non-leap year and `20170431` are all
**accepted**. `_shared/timeformats.is_valid_date_format` is already correct and
records the measurement; do not re-derive it here.

What the length gate catches is a *longer* string, not a shorter one:
`parse(text, ParsePosition)` does not require the input to be consumed, so
`20170101XYZ` would otherwise parse.

The prefix is `getVehicleAndTripIdText(entity) + " start_date is " + startDate`.
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

RULE_ID = "E021"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
