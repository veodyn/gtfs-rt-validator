"""E018: the header timestamp went backwards between two iterations.

`TimestampValidator.java:126-129`, the second arm of the chain, so it can
never coincide with E017 or W007. Same three guards: a non-zero header
timestamp, a previous message, and a non-zero previous header timestamp.

The prefix names both values, and it reads the previous one twice from the
message rather than from the `previousTimestamp` local (`:128`); the two are the
same value, so the port keeps one.

Not gated on `isPosix`, so a decrease between two non-POSIX timestamps still
reports here as well as under E001.
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

RULE_ID = "E018"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """At most one E018, since the header is compared once."""
    for event in events_for(RULE_ID, timestamps, message, ctx):
        yield Occurrence(RULE_ID, event.prefix, event.context)
