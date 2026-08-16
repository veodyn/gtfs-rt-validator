"""S035: a localized image whose media_type is not an image type.

`TranslatedImage.LocalizedImage.media_type`'s comment, at `:1068`:

    The type must start with "image/"

The field exists so a consumer can decide whether it can render the thing at the
other end of the URL before fetching it, and a type outside the `image/` tree
answers that question wrongly whatever the bytes turn out to be.

**The comparison is a prefix and folds case**, because the sentence delegates.
Its subject is "The type", an anaphor whose only antecedent is the line above it
at `:1067`, "IANA media type as to specify the type of image to be displayed",
and `upstream/spec-clauses.json` records that line as this clause's `unit_line`:
the two are one comment unit and the cited sentence cannot be read without the
other. RFC 6838 section 4.2 settles what an IANA media type is here: "Both
top-level type and subtype names are case-insensitive." So `IMAGE/PNG` is the
same media type as `image/png` and does start with `image/`; reporting it would
enforce more than the sentence, which is as much a defect as enforcing less.
Anything under the tree passes, including a subtype nobody here has heard of.

`media_type` is `required`, so every `LocalizedImage` that decoded has one and
there is no absent case to reason about. Experimental status buys no severity
discount: every rule of this tier takes its severity from its own clause's modal
verb, "must" here, and a feed violating this is broken in a way no consumer can
work around. Reporting it as a suggestion would grade it on the message's status
instead of on the sentence.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_translations import localized_images
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S035"

CLAUSE = 'spec: The type must start with "image/"'

MEDIA_TYPE = "media_type"

#: The prefix the clause quotes, spelled once so the comparison and the
#: occurrence text cannot drift apart.
IMAGE_PREFIX = "image/"


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(
            RULE_ID,
            f'{site.path} {MEDIA_TYPE} "{site.image.get(MEDIA_TYPE)}" '
            f'does not start with "{IMAGE_PREFIX}"',
            {ENTITY_PATH_KEY: site.path},
        )
        for site in localized_images(message, ctx)
        if not site.image.get(MEDIA_TYPE).lower().startswith(IMAGE_PREFIX)
    ]
