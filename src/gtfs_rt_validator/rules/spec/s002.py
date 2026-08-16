"""S002: two `FeedEntity` values of one `FeedMessage` sharing an `id`.

`:92`, and a WARNING because the sentence says `should`. The next sentence is
why it is not stronger: "Consequent FeedMessages may contain FeedEntities with
the same id", which is how a DIFFERENTIAL update replaces one. Within a single
message there is no such reading, and the ids exist "only to provide
incrementality support" (`:90`), which a collision defeats.

**Not E052.** That rule reports a `VehicleDescriptor.id` shared by two vehicles
in one message, a different field on a different message; a feed can violate
either without the other, and `tests/test_spec_tier_does_not_shadow_the_jar.py`
shows the jar staying silent on this one's fixture.

One occurrence per repeated id rather than one per entity: the defect is the
collision, so a feed that puts one id on forty entities has made one mistake.
`walk_entities.repeated_ids` keeps first-seen order, which is the order the feed
was written in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.walk_entities import entities
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.walk_entities import Entities
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S002"

CLAUSE = "The id should be unique within a FeedMessage."

SHARED = "entity ID {entity_id} is claimed by {count} entities"


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per id more than one entity claims, in first-seen order."""
    walked = entities(message, ctx)
    return [_found(walked, entity_id) for entity_id in walked.repeated_ids()]


def _found(walked: Entities, entity_id: str) -> Occurrence:
    indexes = [record.index for record in walked.records if record.entity_id == entity_id]
    return Occurrence(
        RULE_ID,
        SHARED.format(entity_id=entity_id, count=len(indexes)),
        {"entityId": entity_id, "entityIndexes": indexes},
    )
