"""S034: two localized images of one `TranslatedImage` that omit their language.

`TranslatedImage.LocalizedImage.language`'s comment, at `:1072`, which is
`TranslatedString.Translation.language`'s sentence restated word for word:

    At most one translation is allowed to have an unspecified language tag.

`TranslatedImage`'s resolution procedure at `:1050` ends the way
`TranslatedString`'s does, with the untagged member as the last resort, so a
second untagged image is unreachable and the choice between the two is
arbitrary.

**Why this is not S032.** The two clauses are the same sentence at two lines on
two messages. `tools/scan_clauses.py` keeps duplicate texts in the proto index
for exactly this reason, and folding them would have lost a rule. A single
module would have to quote one of the two lines and would then be enforcing the
other without citing it.

Presence, not emptiness, for the reason S032 gives.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_translations import images
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S034"

CLAUSE = "spec: At most one translation is allowed to have an unspecified language tag."

LANGUAGE = "language"
LOCALIZED = "localized_image"


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"{site.path} has {untagged} localized images with no {LANGUAGE} tag",
            {ENTITY_PATH_KEY: site.path},
        )
        for site in images(message, ctx)
        for untagged in [
            sum(1 for each in site.translated.get(LOCALIZED) if not each.has(LANGUAGE))
        ]
        if untagged > 1
    ]
