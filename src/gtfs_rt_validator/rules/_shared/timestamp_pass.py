"""What `TimestampValidator` computes once and every branch of it then reads.

`walk_timestamp.py` and `walk_timestamp_stops.py` are two halves of one loop,
split by the file-size hook, and this is the scaffolding both of them need. It
is its own module rather than living in either half because the walk imports the
stop_time_update pass and not the reverse, so anything shared has to sit below
both.

Upstream keeps these as locals of one 270-line method (`:60-62`, `:81`, `:86`).
Naming them is not a redesign: `headerTimestamp` is read at the top and then
consulted by the E012 test inside the entity loop 60 lines later, and
`currentTimeText` is computed once precisely so that every E050 occurrence on
one message names the same second.
"""

from __future__ import annotations

from dataclasses import dataclass

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY

__all__ = [
    "HEADER_PATH",
    "IN_FUTURE_TOLERANCE_SECONDS",
    "MAX_AGE_SECONDS",
    "MINIMUM_REFRESH_INTERVAL_SECONDS",
    "Pass",
    "at",
]

# `:60-62`, upstream's own names and values.
MINIMUM_REFRESH_INTERVAL_SECONDS = 35
MAX_AGE_SECONDS = 65
IN_FUTURE_TOLERANCE_SECONDS = 60

#: Where a header finding sits in a modern report. `--compat` ignores it.
HEADER_PATH = "header"


@dataclass(frozen=True, slots=True)
class Pass:
    """The four values the whole validator shares, computed once per message.

    `header_timestamp` is read with no `has` test, so 0 means "absent" and is
    the discriminator the E048-versus-W001 fork and the two E012 sites branch
    on. `current_time_text` is `posixToClock` of the current time, rendered once
    at `:81`.
    """

    header_timestamp: int
    current_time_millis: int
    current_time_text: str
    timezone: str


def at(path: str) -> dict[str, object]:
    """One event's `entityPath`, the context a rule inside a loop cannot rebuild."""
    return {ENTITY_PATH_KEY: path}
