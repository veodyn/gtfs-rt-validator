"""E050: a timestamp further into the future than the tolerance allows.

Three emission sites, `TimestampValidator.java:113-117` for the header,
`:158-165` for a TripUpdate and `:285-292` for a VehiclePosition. Each requires
the timestamp to be non-zero and POSIX first, and then
`TimestampUtils.isInFuture(currentTimeMillis, timestamp, 60)`, which is
**strictly greater** than the tolerance: exactly 60 seconds ahead passes and 61
reports. stop_time_update times are not checked.

**This rule's occurrence text is the only one upstream asserts byte for byte
anywhere in its suite** (`test/TimestampValidatorTest.java:1117`), which makes it
the single best oracle for the timezone-to-report path in this project.
`tests/test_rule_e050.py` ports that assertion exactly.

Two details of the text. The parenthesised number after the timestamp's clock
string is raw POSIX **seconds**, and the one after the current time's is raw
**milliseconds**. And `currentTimeText` is rendered once for the whole message
(`:81`), so three future timestamps name one "now" rather than three, which a
per-occurrence render could land a second apart from.
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

RULE_ID = "E050"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Every E050 the shared walk saw, header first and then entity order."""
    for event in events_for(RULE_ID, timestamps, message, ctx):
        yield Occurrence(RULE_ID, event.prefix, event.context)
