"""W008: the header timestamp is more than 65 seconds old.

`TimestampValidator.java:109-112`. Requires the header timestamp to be
non-zero and POSIX, and then `getAge(currentTimeMillis, headerTimestamp)` to
exceed `MAX_AGE_SECONDS = 65` seconds, strictly, in **milliseconds**: an age of
exactly 65000 ms passes.

The "current time" is not the wall clock. Upstream computes one timestamp per
file, from the modification time or from the file name under `-sort name`, and
hands it to every validator (`BatchProcessor.java:220-232`), which is what makes
an archive replay reproducible. `runner/clock.py` is that.

The prefix renders the age as minutes and seconds with `TimeUnit` truncation,
which `_shared/timestamp_text.stale_header` reproduces; W008 itself never reads
the agency timezone, though E050 in the same block does.
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

RULE_ID = "W008"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """At most one W008, since the header is checked once."""
    for event in events_for(RULE_ID, timestamps, message, ctx):
        yield Occurrence(RULE_ID, event.prefix, event.context)
