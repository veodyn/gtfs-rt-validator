"""E039: a FULL_DATASET feed carries `entity.is_deleted`.

Ported from `validation/rules/HeaderValidator.java:64-71`, the third of that
validator's three conditions and the **second** of its three output groups
(`:77-79`); the groups are emitted E038, E039, E049 while the conditions are
written E038, E049, E039.

```java
if (feedMessage.getHeader().getIncrementality().equals(Incrementality.FULL_DATASET)) {
    for (FeedEntity entity : feedMessage.getEntityList()) {
        if (entity.hasIsDeleted()) {
            RuleUtils.addOccurrence(E039, "entity ID " + entity.getId()
                + " has is_deleted=" + entity.getIsDeleted(), errorListE039, _log);
        }
    }
}
```

Three things the Java says that a reading of the rule's title does not.

**An absent `incrementality` is scanned.** `getIncrementality()` is read with no
`hasIncrementality()` guard, and FULL_DATASET is the enum's zero value and so
protobuf's default for an absent field. A header that never mentions
incrementality therefore takes exactly the same branch an explicit FULL_DATASET
one does. Upstream's own test has to set DIFFERENTIAL to reach zero occurrences,
which is the tell.

**The test is presence, not truth.** `hasIsDeleted()` fires on
`is_deleted = false` as well, and the false goes into the prefix. Java
concatenates a `boolean` as lower-case `true`/`false`, where Python's `str`
would capitalise it, so the rendering goes through `_shared/javafmt.java_bool`
rather than an f-string.

**One occurrence per entity, in entity order**, and the loop has no break: a
feed with four deleted entities reports four times.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.javafmt import java_bool
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only, both of them. `runner.context` reaches the static
    # layer and the sibling package, and nothing under `rules/` may import that
    # at run time; `tests/test_only_adapter_touches_the_sibling.py` is the check.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "E039"

#: `FeedHeader.Incrementality.FULL_DATASET`. The number rather than the name,
#: because the decoder hands a rule the enum's value; both schemas declare
#: `{"FULL_DATASET": 0, "DIFFERENTIAL": 1}`, and its being zero is the whole
#: reason an absent incrementality lands in this branch.
FULL_DATASET = 0

DELETED_FIELD = "is_deleted"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per entity carrying `is_deleted`, on a FULL_DATASET feed."""
    if message.get("header").get("incrementality") != FULL_DATASET:
        return None
    return [
        _found(index, entity)
        for index, entity in enumerate(message.get("entity"))
        if entity.has(DELETED_FIELD)
    ]


def _found(index: int, entity: Msg) -> Occurrence:
    deleted = entity.get(DELETED_FIELD)
    entity_id = entity.get("id")
    return Occurrence(
        RULE_ID,
        f"entity ID {entity_id} has {DELETED_FIELD}={java_bool(deleted)}",
        {ENTITY_PATH_KEY: f"entity[{index}]", "entityId": entity_id, "isDeleted": deleted},
    )
