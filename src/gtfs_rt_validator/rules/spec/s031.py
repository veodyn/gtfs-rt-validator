"""S031: a `TranslatedString` written with no translation in it.

`TranslatedString.translation`'s comment, at `:1036`:

    At least one translation must be provided.

A `TranslatedString` is the whole of what a field says, so one carrying no
translation says nothing at all in any language: the resolution procedure at
`:1011` walks the list looking for a language match and then for an untagged
translation, and an empty list fails both and leaves the consumer with nothing
to render.

**The rule names no field.** It is about the type, which sits on fourteen fields
of two messages at this pin, and `_shared/walk_translations.py` finds them from
the descriptors. A field added at a later pin is covered the day the schema
regenerates. An *absent* field is not a site: the getter answers a default
instance holding zero translations, so a rule that read defaults would report
every alert in the feed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_translations import translations
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S031"

CLAUSE = "spec: At least one translation must be provided."


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"{site.path} was written with no translation",
            {ENTITY_PATH_KEY: site.path},
        )
        for site in translations(message, ctx)
        if not site.translated.get("translation")
    ]
