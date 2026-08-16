"""P004: consecutive header timestamps more than 30 seconds apart, up to 35.

The band W007 cannot reach, and the reason it is a new id rather than a change
to W007: `rules/upstream/w007.py` is a compat byte contract, and mode is
descriptor, registry and writer rather than a branch inside a rule. The two
bands are disjoint by construction, so no feed is reported twice.

**The two edges, measured against the pinned jar rather than read off a
docstring.** One invocation per interval over a two-file run, each file's clock
its own mtime:

| interval, seconds | jar |
|---|---|
| 20 | nothing |
| 30 | nothing |
| 33 | nothing |
| 35 | nothing |
| 36 | W007 |
| 40 | W007 |

So `MINIMUM_REFRESH_INTERVAL_SECONDS = 35` really is compared strictly, and the
band `30 < interval <= 35` is exactly what upstream cannot reach. `BAND_UPPER`
is imported from `_shared/timestamp_pass` rather than written out here, so a pin
that moved upstream's threshold moves this band with it instead of opening a gap
or an overlap. Upstream's own `data/rules.json` description says "at least every
30 seconds" while its threshold is 35, so upstream contradicts both the document
and itself; neither is this project's to fix under `--compat`.

**Both timestamps are read as the `uint64` the proto declares.** W007 reads them
through `_shared/javafmt.int64`, because protobuf-java hands a Java rule the
signed `long` and that narrowing reaches upstream's output. A practice rule has
no jar to match. That divergence cannot make the two bands overlap: the signed
and unsigned intervals differ only when one operand is at or above 2^63, and in
that case the signed comparison makes the pair E018's rather than W007's.

**A zero header timestamp is an absent one**, which is upstream's own reading
(`walk_timestamp.py` returns before the previous-message chain when the current
header timestamp is 0, and treats a previous 0 as no previous message at all).
Its absence is W001's or E048's finding; reading it as 1970 would make this rule
fire on any feed whose previous message declared nothing.

"Previous" is the previous message of the same role, which `runner/context.py`
settles once for every rule that reads one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.timestamp_pass import (
    HEADER_PATH,
    MINIMUM_REFRESH_INTERVAL_SECONDS,
    at,
)
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P004"

CLAUSE = (
    "GTFS Realtime feeds should be refreshed at least once every 30 seconds, or whenever the "
    "information represented within the feed (position of a vehicle) changes, whichever is more "
    "frequent."
)

#: The document's number, and the edge is exclusive: "at least once every 30
#: seconds" is satisfied by exactly 30, so 30 is nobody's finding.
BAND_LOWER = 30

#: Where W007 starts, imported so the two cannot drift apart. Inclusive here
#: because W007's comparison is strict, measured at 35 silent and 36 firing.
BAND_UPPER = MINIMUM_REFRESH_INTERVAL_SECONDS

REPORTED = (
    "{interval} second interval between consecutive header.timestamps, "
    f"which is more than the recommended {BAND_LOWER}"
)


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """At most one occurrence, since a message has one header."""
    if ctx.previous is None:
        return None
    previous = ctx.previous.get("header").get("timestamp")
    current = message.get("header").get("timestamp")
    if previous == 0 or current == 0:
        return None
    interval = current - previous
    if not BAND_LOWER < interval <= BAND_UPPER:
        return None
    return [
        Occurrence(
            RULE_ID,
            REPORTED.format(interval=interval),
            {
                **at(HEADER_PATH),
                "intervalSeconds": interval,
                "previousTimestamp": previous,
                "timestamp": current,
            },
        )
    ]
