"""W007: consecutive header timestamps more than 35 seconds apart.

`TimestampValidator.java:130-133`, the third arm of an if/else-if chain
(`:123-133`) rather than an independent test. Equal timestamps fire E017, a
decreased one fires E018, and only a strictly greater interval is compared
against `MINIMUM_REFRESH_INTERVAL_SECONDS = 35`. So W007 can never coincide with
either of the other two, and the comparison is strict: an interval of exactly 35
passes.

Gated on the header timestamp being non-zero, on there being a previous message
at all, and on *its* header timestamp being non-zero (`:120`). Not gated on
`isPosix`, so two timestamps outside the POSIX window still produce an interval.

The suffix in the manifest reads "which is less than the recommended interval of
35 seconds" where the condition is "more than". That is upstream's text and the
rule title says the opposite; neither is this project's to fix under `--compat`.

"Previous" is per feed role here, which under `--compat` is upstream's single
unnamed feed and therefore upstream's own behaviour unchanged. `runner/context.py`
says why a cross-role comparison would be meaningless.
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

RULE_ID = "W007"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """At most one W007, since the header is compared once."""
    for event in events_for(RULE_ID, timestamps, message, ctx):
        yield Occurrence(RULE_ID, event.prefix, event.context)
