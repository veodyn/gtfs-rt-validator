"""S025: an alert that sets the deprecated `active_period`.

`Alert.active_period`'s comment ends at `:628`:

    Should not be used - for backwards-compatibility only.

and the declaration below it is `repeated TimeRange active_period = 1
[deprecated = true]`. `communication_period` and `impact_period` are what
replaced it, splitting "when to show this" from "when this bites".

**The field name is checked against the schema at import**, the way
`_shared/schedule_relationship.py` checks every enum member it names. A pin that
undeprecated the field, or renamed it, would otherwise leave this rule firing on
a supported field with nothing red to say so. The check reads the option rather
than the sentence, so the two halves of the same site have to agree.

One occurrence per alert rather than one per range: the defect is using the
field at all, and a producer with eight ranges made one mistake.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_entities import entities
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S025"

CLAUSE = "spec: Should not be used - for backwards-compatibility only."

ALERT = "alert"


def _deprecated(message_name: str, field_name: str) -> str:
    """`field_name`, having checked the pin still marks it `[deprecated = true]`."""
    for field in SCHEMA.message(message_name).fields:
        if field.name == field_name and field.deprecated:
            return field_name
    raise ValueError(f"{message_name}.{field_name} is not deprecated at this pin")


DEPRECATED_FIELD = _deprecated("Alert", "active_period")


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"alert ID {record.entity_id} sets {DEPRECATED_FIELD}, which this pin deprecates",
            {ENTITY_PATH_KEY: f"{record.path}.{ALERT}"},
        )
        for record in entities(message, ctx).carrying(ALERT)
        if record.entity.get(ALERT).get(DEPRECATED_FIELD)
    ]
