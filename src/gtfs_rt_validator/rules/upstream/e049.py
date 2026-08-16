"""E049: a v2-or-higher header does not populate `incrementality`.

Ported from `validation/rules/HeaderValidator.java:55-62`, the second of that
validator's three conditions and the **last** of its three output groups
(`:80-82`).

```java
try {
    if (GtfsUtils.isV2orHigher(feedMessage.getHeader())
            && !feedMessage.getHeader().hasIncrementality()) {
        RuleUtils.addOccurrence(E049, "", errorListE049, _log);
    }
} catch (Exception e) {
    _log.error("Error checking header version for E049: " + e);
}
```

**The catch is the rule.** `isV2orHigher` hands the version field to
`Float.parseFloat` with no `has` guard, so an absent or non-numeric version
throws `NumberFormatException`, and this call site swallows it: the feed is
never asked about `incrementality` at all. That looks like a bug and
reproducing it is the requirement, because `TimestampValidator.java:87-100`
catches the identical failure with its own flag already initialised to `true`
and therefore *does* log E048. A helper that answered a tidy `False` would
collapse the two into one behaviour and quietly lose E048; `_shared/versions.py`
raises for that reason, and this is the half that has to swallow.

The `except` here is narrower than Java's `catch (Exception)`, deliberately.
`is_v2_or_higher` raises `ValueError` for exactly the input `Float.parseFloat`
rejects, and that is a fact about the feed. Anything else out of this line would
be a bug in this repository, and Java's wider catch is not a reason to hide it:
`ruff`'s `BLE` rule says the same thing about blind excepts.

**The prefix is the empty string.** Everything a reader sees comes from the
rule's suffix in the manifest, and nothing varies per occurrence.

At most one occurrence per message: the header is one field, not a list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.versions import is_v2_or_higher
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only, both of them. `runner.context` reaches the static
    # layer and the sibling package, and nothing under `rules/` may import that
    # at run time; `tests/test_only_adapter_touches_the_sibling.py` is the check.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "E049"

INCREMENTALITY_FIELD = "incrementality"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence when the version parses to 2.0 or more and the header has
    no `incrementality`, and nothing at all when the version does not parse."""
    header = message.get("header")
    try:
        v2_or_higher = is_v2_or_higher(header)
    except ValueError:
        # Upstream logs and moves on, so this feed is never checked. See the
        # module docstring: the same failure makes TimestampValidator emit E048.
        return None
    if v2_or_higher and not header.has(INCREMENTALITY_FIELD):
        return [Occurrence(RULE_ID, "", {ENTITY_PATH_KEY: "header"})]
    return None
