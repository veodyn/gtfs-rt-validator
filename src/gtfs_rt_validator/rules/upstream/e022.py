"""E022: stop_time_update times that do not increase between two stops.

`TimestampValidator.java:193-245`, and the most intricate occurrence
generator upstream has: **eight independent `if`s**, four when this
stop_time_update carried an arrival and four when it carried a departure, all of
which can fire from one stop_time_update.

Each block asks its own field first and the other field second, less-than before
equal-to. `Objects.equals` is a separate test from `<` rather than a merged
`<=`, because the two produce different occurrence text, and merging them loses
occurrences that upstream writes.

The state that makes this rule what it is lives in
`rules/_shared/walk_timestamp_stops.py`: `previousArrivalTime` and
`previousDepartureTime` advance **only when that field was present on this
stop_time_update** (`:256-263`), so "previous stop" means "the most recent stop
that had this field" and a comparison reaches back past a stop_time_update that
carried only the other one.

Every occurrence embeds two clock strings rendered in the agency timezone, so a
wrong zone corrupts all of them. There is no de-duplication: one
stop_time_update can produce four occurrences, and upstream reports all four.
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

RULE_ID = "E022"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Every E022 the shared walk saw, stop by stop and case by case in order."""
    for event in events_for(RULE_ID, timestamps, message, ctx):
        yield Occurrence(RULE_ID, event.prefix, event.context)
