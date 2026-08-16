r"""S036: a localized image URL that is not fully qualified.

`TranslatedImage.LocalizedImage.url`'s comment, at `:1064`:

    The URL should be a fully qualified URL that includes http:// or https://,
    and any special characters in the URL must be correctly escaped.

**The rule enforces the scheme half whole and the escaping half in part.** The
sentence mixes a `should` and a `must`, so the clause index permits either
severity; one rule declares one severity, and the scheme half is the `should`,
so this is a WARNING and the escaping half is reported at the weaker of the two
the sentence allows. `upstream/spec-clause-verdicts.json` records the split on
`1064#1` and names the part that is not checked.

**Which part of "correctly escaped" a feed decides.** Not all of it: a URL whose
characters were never escaped and one that needed no escaping are the same
bytes, so a literal `?`, `&` or `+` says nothing about what the producer did.
That is the R2 half and it stays rejected. But a character RFC 3986 does not let
a URI carry at all is decidable from the bytes alone: a space, a control
character, a non-ASCII character or one of ``"<>\^`{|}`` is a special character
that was not escaped, whatever the producer intended. So is a `%` that does not
begin a two-hex-digit escape, which is an escape that is not correct. Reporting
those two is the sentence, and reading a literal reserved character as evidence
of anything would be wider than it.

**The scheme comparison folds case** for the reason S035's does: the clause asks
for "a fully qualified URL", and RFC 3986 section 3.1 says "Although schemes are
case-insensitive, the canonical form is lowercase". `HTTPS://example.com/a.png`
is that URL, so reporting it would enforce more than the sentence.

A feed's image URL is dereferenced by a consumer that has no page to resolve it
against, so a relative or scheme-relative URL resolves to nothing at all. `url`
is `required`, so it is always present; present and empty is still not a fully
qualified URL and is reported. One image is one finding: a URL that fails both
halves reports the scheme, which is the half the rule is named for.
"""

from __future__ import annotations

from collections.abc import Sequence
from string import ascii_letters, digits, hexdigits
from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_translations import localized_images
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S036"

CLAUSE = (
    "spec: The URL should be a fully qualified URL that includes http:// or https://, "
    "and any special characters in the URL must be correctly escaped."
)

URL = "url"

#: The two the clause names, spelled once so the test and the text agree.
SCHEMES = ("http://", "https://")

#: Every character RFC 3986 lets a URI carry literally: unreserved, the two
#: delimiter sets, and the `%` an escape begins with. A URL carrying anything
#: else carries a special character that was not escaped.
LITERAL = frozenset(ascii_letters + digits + "-._~" + ":/?#[]@" + "!$&'()*+,;=" + "%")

HEX = frozenset(hexdigits)

#: How much of the URL an escape is, `%` included.
ESCAPE_WIDTH = 3


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, f'{site.path} {URL} "{url}" {said}', {ENTITY_PATH_KEY: site.path})
        for site in localized_images(message, ctx)
        for url in [site.image.get(URL)]
        for said in [_complaint(url)]
        if said is not None
    ]


def _complaint(url: str) -> str | None:
    """The first thing the clause has to say about `url`, if it has one."""
    if not url.lower().startswith(SCHEMES):
        return f"does not begin {' or '.join(SCHEMES)}"
    return _unescaped(url)


def _unescaped(url: str) -> str | None:
    """The first special character `url` carries that it may not, if any.

    A character outside `LITERAL` is one a URI cannot carry at all, and it is
    named by codepoint because several of them are invisible. A `%` that does
    not begin two hex digits is an escape that is not correct.
    """
    for index, character in enumerate(url):
        if character not in LITERAL:
            return f"leaves U+{ord(character):04X} unescaped"
        escape = url[index : index + ESCAPE_WIDTH]
        if character == "%" and (len(escape) < ESCAPE_WIDTH or not HEX.issuperset(escape[1:])):
            return f'does not correctly escape "{escape}"'
    return None
