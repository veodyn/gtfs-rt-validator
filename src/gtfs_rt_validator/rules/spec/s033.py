"""S033: a `TranslatedImage` written with no localized image in it.

`TranslatedImage.localized_image`'s comment, at `:1085`:

    At least one localized image must be provided.

The same argument as S031's on the other internationalised type: the resolution
procedure at `:1050` walks the list for a language match and then for an
untagged image, and an empty list fails both, so the field says nothing a
consumer can display.

`TranslatedImage` sits on one field at this pin, `Alert.image`, and the rule
still goes through `_shared/walk_translations.py` rather than reading that field
by name. One site is exactly the case a hand-written list looks adequate for and
is silently wrong about at the pin that adds a second.
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

RULE_ID = "S033"

CLAUSE = "spec: At least one localized image must be provided."


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f"{site.path} was written with no localized image",
            {ENTITY_PATH_KEY: site.path},
        )
        for site in images(message, ctx)
        if not site.translated.get("localized_image")
    ]
