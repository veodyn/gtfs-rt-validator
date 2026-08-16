"""E025: a stop_time_update whose departure is before its own arrival.

`TimestampValidator.java:246-253`, inside the departure block and emitted
after that stop's four E022 comparisons. **Within one stop_time_update only**,
never across two, which is what separates it from E022.

The condition reads `stopTimeUpdate.getArrival().hasTime()` with no
`hasArrival()` guard. That is safe rather than a bug: an absent arrival decodes
to the default instance, whose `hasTime()` is false. Equal times pass; only a
strictly earlier departure reports.

Both clock strings are rendered in the agency timezone, and the arrival is
rendered a second time here rather than reusing the arrival block's local
(`:250`), which produces the same bytes.
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

RULE_ID = "E025"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Every E025 the shared walk saw, in stop_time_update order."""
    for event in events_for(RULE_ID, timestamps, message, ctx):
        yield Occurrence(RULE_ID, event.prefix, event.context)
