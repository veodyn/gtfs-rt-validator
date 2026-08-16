"""S027: an alert whose `cause_detail` has no `cause` to refine.

The `Cause` enum's own comment, at `:644`:

    If cause_detail is included, then Cause must also be included.

`:720` restates it verbatim on the `cause_detail` field. The verdict file folds
that second sentence into this rule rather than making it a second one, because
a second rule would report the same alert twice; the citation quotes the
enum-side sentence, which is where the constraint is declared.

`cause_detail` is agency-specific wording for a cause a consumer may not be able
to render, so it is a refinement of the enum rather than a replacement for it. A
consumer that does not understand the detail has nothing left to fall back on.

**Presence, not value.** `Alert.cause` is declared `[default = UNKNOWN_CAUSE]`,
so an alert that names no cause reads `UNKNOWN_CAUSE` back through the getter and
the value cannot distinguish the two. A producer that wrote `UNKNOWN_CAUSE`
explicitly has included the field, which is what the sentence asks for.

S028 is the identical shape on `effect_detail` and `effect`. They are two rules
because they are two sentences at two lines about two fields, and a single
module would have to pick one citation and misquote the other.
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

RULE_ID = "S027"

CLAUSE = "spec: If cause_detail is included, then Cause must also be included."

ALERT = "alert"
DETAIL = "cause_detail"
ENUM = "cause"


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
