"""E048: a v2.0-or-higher header with no timestamp.

`TimestampValidator.java:87-96`, and the interesting half is the `catch`.

```java
boolean isV2orHigher = true;
try {
    isV2orHigher = GtfsUtils.isV2orHigher(feedMessage.getHeader());
} catch (Exception e) {
    _log.error("Error checking header version for E048/W001, logging as E048: " + e);
}
if (isV2orHigher) { E048 } else { W001 "header" }
```

The flag is `true` **before** the call, so a version that `Float.parseFloat`
refuses leaves it true and this rule fires rather than W001. `""` is such a
version; a truly absent one is not reachable, because `gtfs_realtime_version` is
`required` at both pins, so a message without it fails `isInitialized` here and
`parseFrom` upstream and the file is skipped before any rule runs.
That is the exact opposite of `HeaderValidator.java:60-62`, which catches
the identical exception and skips E049 entirely. Both are compat surface, which
is why `_shared/versions.is_v2_or_higher` raises: a helper that answered a tidy
`False` would make this half unreachable.

**The prefix is the empty string** (`:96`), so everything a reader sees is the
rule's suffix in the manifest. At most one per message: the header is one field.

Reached only when the header timestamp is 0, which is a `getTimestamp()` read
with no `has` test, so absent and explicitly zero are one case here.
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

RULE_ID = "E048"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """One occurrence when the header has no timestamp and is not below v2.0."""
    for event in events_for(RULE_ID, timestamps, message, ctx):
        yield Occurrence(RULE_ID, event.prefix, event.context)
