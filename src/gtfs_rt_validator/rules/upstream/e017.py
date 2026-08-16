"""E017: the header timestamp did not change though the feed content did.

`TimestampValidator.java:123-125`, the first arm of the if/else-if chain
that also holds E018 and W007. Requires the header timestamp to be non-zero, a
previous message to exist, and its header timestamp to be non-zero too.

**The "content changed" half is not tested here at all.** Upstream enforces it
upstream of the validator: `BatchProcessor.java:214-218` skips a file whose MD5
matches the previous one, and `TimestampValidator.java:66-68` throws when the
two messages are equal. This project reproduces the first and deliberately not
the second; `_shared/walk_timestamp._previous_header_timestamp` records why, and
`runner/dedupe.py` is the MD5 skip.

"Previous" is the previous message of the same feed role. Under `--compat` there
is one unnamed role, so that is upstream's behaviour unchanged.
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

RULE_ID = "E017"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """At most one E017, since the header is compared once."""
    for event in events_for(RULE_ID, timestamps, message, ctx):
        yield Occurrence(RULE_ID, event.prefix, event.context)
