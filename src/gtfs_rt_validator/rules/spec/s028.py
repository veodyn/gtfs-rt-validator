"""S028: an alert whose `effect_detail` has no `effect` to refine.

The `Effect` enum's own comment, at `:662`:

    If effect_detail is included, then Effect must also be included.

`:724` restates it verbatim on the `effect_detail` field, and the verdict file
folds that sentence into this rule for the reason S027's docstring gives: a
second rule would report the same alert twice.

`effect_detail` is agency-specific wording for an effect a consumer may not be
able to render, so it refines the enum rather than replacing it, and an alert
that supplies only the detail leaves a consumer that cannot read it with nothing.

**Presence, not value.** `Alert.effect` is declared `[default = UNKNOWN_EFFECT]`,
so the value cannot tell an omitted field from an explicit `UNKNOWN_EFFECT`. A
producer that wrote the default has included the field.

S027 is the identical shape on `cause_detail` and `cause`. Two sentences at two
lines about two fields are two rules: a single module would have to pick one
citation and misquote the other, and the citation gate compares bytes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_entities import entities
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S028"

CLAUSE = "spec: If effect_detail is included, then Effect must also be included."

ALERT = "alert"
DETAIL = "effect_detail"
ENUM = "effect"


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"alert ID {record.entity_id} sets {DETAIL} without {ENUM}",
            {ENTITY_PATH_KEY: f"{record.path}.{ALERT}"},
        )
        for record in entities(message, ctx).carrying(ALERT)
        for alert in [record.entity.get(ALERT)]
        if alert.has(DETAIL) and not alert.has(ENUM)
    ]
