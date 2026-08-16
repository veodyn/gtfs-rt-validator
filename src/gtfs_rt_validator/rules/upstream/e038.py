"""E038: `header.gtfs_realtime_version` is a value upstream does not know.

Ported from `validation/rules/HeaderValidator.java:50-53`, the first of that
validator's three conditions and the first of its three output groups:

```java
if (!GtfsUtils.isValidVersion(feedMessage.getHeader())) {
    RuleUtils.addOccurrence(E038, "header.gtfs_realtime_version of "
        + feedMessage.getHeader().getGtfsRealtimeVersion(), errorListE038, _log);
}
```

Two things worth knowing before changing this. **An absent version is valid**:
`isValidVersion` starts with `!hasGtfsRealtimeVersion()`, so the field only has
to be `"1.0"` or `"2.0"` when it is there at all. That branch is unreachable
through a decode, because the field is `required` and both protobuf-java and
`proto/decode.py` refuse a header without it, but it is the first thing the
helper tests and `_shared/versions.py` reproduces it. And the test is **string
equality, not a parse**: `"1.00"`, `" 2.0"` and `"2.0f"` are all invalid
versions, while `"3.0"` is both an invalid version and v2-or-higher, which is
how one header can be reported here and checked by E049 on the same message.

At most one occurrence per message: the header is one field, not a list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.versions import is_valid_version
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only, both of them. `runner.context` reaches the static
    # layer and the sibling package, and nothing under `rules/` may import that
    # at run time; `tests/test_only_adapter_touches_the_sibling.py` is the check.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "E038"

#: The field, spelled once. It appears in the prefix as well as in the read,
#: and upstream's prefix uses the proto name rather than the Java getter.
VERSION_FIELD = "gtfs_realtime_version"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence when the header names a version that is not 1.0 or 2.0."""
    header = message.get("header")
    if is_valid_version(header):
        return None
    version = header.get(VERSION_FIELD)
    return [
        Occurrence(
            RULE_ID,
            f"header.{VERSION_FIELD} of {version}",
            {ENTITY_PATH_KEY: "header", "gtfsRealtimeVersion": version},
        )
    ]
