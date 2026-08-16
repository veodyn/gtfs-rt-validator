"""S024: a TripDescriptor transmitting a deprecated schedule_relationship.

`TripDescriptor.ScheduleRelationship.ADDED`'s comment, at `:853`:

    This value has been deprecated as the behavior was unspecified.

The next two lines say what to use instead, DUPLICATED for an extra trip that
copies a scheduled one and NEW for an extra trip that copies nothing, and
`:856` marks the member `[deprecated = true]`.

**Which members are deprecated comes from the schema, not from a name here.**
`Schema.deprecated_enum_values` carries the option and
`_shared/schedule_relationship.DEPRECATED_TRIP_RELATIONSHIPS` exposes it, so a
member deprecated at a later pin reaches this rule through the regenerated
schema rather than through a code change. An earlier draft of this rule compared
the member name instead, because the schema generator dropped the option;
`tools/gen_schema_current.py` was fixed before this cohort landed, and
`tests/test_schema_current.py` asserts the option survives regeneration.

**Only a value a producer transmitted is reported.** proto2 resolves an absent
`schedule_relationship` to `SCHEDULED`, so if a later pin ever deprecated that
member, a rule reading the resolved value would report every descriptor in every
feed, including the ones that said nothing at all. Reading `declared` costs this
rule nothing today, `ADDED` being 1 and never a default, and it is what stops
the schema-driven half from becoming a liability.

E003 and E016 both branch on `ADDED` and neither objects to it, which is why
this is a new id rather than a branch in either.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import (
    DEPRECATED_TRIP_RELATIONSHIPS,
    relationships,
)
from gtfs_rt_validator.rules._shared.trip_descriptor_spec import trip_text
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S024"

CLAUSE = "spec: This value has been deprecated as the behavior was unspecified."


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"{trip_text(found.trip)} uses schedule_relationship {found.relationship}, "
            f"which this pin deprecates",
            {ENTITY_PATH_KEY: found.path},
        )
        for found in relationships(message, ctx)
        if found.declared and found.relationship in DEPRECATED_TRIP_RELATIONSHIPS
    ]
