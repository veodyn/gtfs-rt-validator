"""S032: two translations of one string that both omit their language tag.

`TranslatedString.Translation.language`'s comment, at `:1024`:

    At most one translation is allowed to have an unspecified language tag.

The resolution procedure at `:1011` ends with "If some translation has an
unspecified language code, that translation is picked", so the untagged
translation is the last resort and a second one is unreachable. Which of the two
a consumer picks is then arbitrary, and two consumers may render one alert
differently from the same bytes.

**Presence, not emptiness.** A translation carrying `language = ""` has
specified its tag, badly. What the clause is about is the field being absent,
which is the case its own sentence before this one blesses: "Can be omitted if
the language is unknown or if no i18n is done at all for the feed."

One occurrence per `TranslatedString` rather than per translation: the defect is
the string having two last resorts, and the count is how many it has. S034 is
the same sentence on `TranslatedImage.LocalizedImage`, at a different line and on
a different message, which is why it is a second rule.
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

RULE_ID = "S032"

CLAUSE = "spec: At most one translation is allowed to have an unspecified language tag."

LANGUAGE = "language"


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"{site.path} has {untagged} translations with no {LANGUAGE} tag",
            {ENTITY_PATH_KEY: site.path},
        )
        for site in translations(message, ctx)
        for untagged in [
            sum(1 for each in site.translated.get("translation") if not each.has(LANGUAGE))
        ]
        if untagged > 1
    ]
