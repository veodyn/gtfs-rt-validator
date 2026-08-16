"""S001: a `FeedEntity` that carries no payload, or more than one.

`:106`, on the six payload fields of `FeedEntity`. The parenthesis is half the
predicate and not a footnote: a DIFFERENTIAL feed deletes an entity by id, so
`is_deleted` with nothing beside it is the intended shape rather than a defect.
Presence is not enough there, unlike E039's `hasIsDeleted()`: the clause exempts
an entity that is *being deleted*, and `is_deleted = false` says it is not.

**The payload set is the descriptor's, not a tuple written here.**
`_shared/walk_entities.payload_names` reads every message-typed field of
`FeedEntity`, which is exactly the payload set at both pins: `id` is a string
and `is_deleted` a bool. A hand-written list would fail silently in the one
direction that matters, since a payload it did not name would read as no payload
at all and this rule would report a correct entity.

Nothing in the 56 looks at the entity's payload count. `--compat` decodes three
of the six as unknown fields, so a leak of this rule into a compat run would be
visible rather than masked, which is why it is one of the seven rules
`tests/test_compat_excludes_the_cited_tiers.py` names as proof that the
descriptor is not a guard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_entities import entities
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.walk_entities import EntityRecord
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S001"

CLAUSE = "Exactly one of the following fields must be present (unless the entity is being deleted)."

NONE_AT_ALL = "entity ID {entity_id} carries no payload"

TOO_MANY = "entity ID {entity_id} carries {count} payloads: {payloads}"


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per live entity that does not carry exactly one payload."""
    return [
        _found(record)
        for record in entities(message, ctx).records
        if record.payload is None and not record.is_deleted
    ]


def _found(record: EntityRecord) -> Occurrence:
    """`payload` answers `None` for both defects, so the text says which."""
    if record.payloads:
        prefix = TOO_MANY.format(
            entity_id=record.entity_id,
            count=len(record.payloads),
            payloads=", ".join(record.payloads),
        )
    else:
        prefix = NONE_AT_ALL.format(entity_id=record.entity_id)
    return Occurrence(
        RULE_ID,
        prefix,
        {
            ENTITY_PATH_KEY: record.path,
            "entityId": record.entity_id,
            "payloads": list(record.payloads),
        },
    )
