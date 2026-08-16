"""S029: an alert description that repeats its header word for word.

`Alert.description_text`'s comment, at `:689`:

    The information in the description should add to the information of the
    header.

**This rule is deliberately narrower than its clause, and it is the only rule in
the tier that is.** Whether one string adds information to another is not
decidable in general. Equality is the one case where it provably adds none, so
the rule enforces a strict subset of the sentence it cites. That is stated here
and in the manifest note, because a rule quietly weaker than its citation is the
failure the citation gate exists to prevent.

**What "identical" means, since a `TranslatedString` is not a string.** Two of
them are identical when they carry the same translations in the same order with
the same language tags. Order matters because the proto's own resolution rule at
`:1011` picks the *first* matching translation, so two orders answer differently
for a reader whose language matches more than one. A language tag that is
present on one and absent on the other is a difference for the same reason.

**Two empty `TranslatedString`s are not reported here.** They are equal, and
each is already S031's finding: a field written with no translation at all. A
third occurrence saying the description adds nothing would describe the same
alert a third time, so the comparison is made only when the header has something
to add to.
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

RULE_ID = "S029"

CLAUSE = "spec: The information in the description should add to the information of the header."

ALERT = "alert"
HEADER = "header_text"
DESCRIPTION = "description_text"

Said = tuple[tuple[str, str | None], ...]


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"alert ID {record.entity_id} {DESCRIPTION} repeats {HEADER} and adds nothing to it",
            {ENTITY_PATH_KEY: f"{record.path}.{ALERT}"},
        )
        for record in entities(message, ctx).carrying(ALERT)
        for alert in [record.entity.get(ALERT)]
        if alert.has(HEADER) and alert.has(DESCRIPTION)
        for header in [_said(alert.get(HEADER))]
        if header and header == _said(alert.get(DESCRIPTION))
    ]


def _said(translated: Msg) -> Said:
    """What a `TranslatedString` says, as a comparable value.

    The language is carried as `None` when absent rather than as the empty
    string the getter would answer, so a translation that omits the tag is not
    equal to one that sets it to nothing.
    """
    return tuple(
        (each.get("text"), each.get("language") if each.has("language") else None)
        for each in translated.get("translation")
    )
