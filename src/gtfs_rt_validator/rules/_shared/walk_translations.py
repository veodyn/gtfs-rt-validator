"""Every internationalised value in a message, wherever the schema puts one.

S031 checks that a present `TranslatedString` carries at least one translation
and S032 that at most one of them omits a language tag. Neither is about any
particular field: they are about the type, and the type appears on fourteen
fields of two messages at this pin, eight on `Alert` and six on `Stop`.

**`TranslatedImage` is the same walk over a second type**, which is why S033 and
S034 read this module rather than a copy of it. The proto gives that message the
same two constraints in the same words, "At least one localized image must be
provided" and "At most one translation is allowed to have an unspecified
language tag", and it appears on one field at this pin, `Alert.image`. One site
is exactly the case a hand-written list looks adequate for and is wrong about at
the next pin, so it is walked rather than reached for by name. The two
accessors are separate functions rather than one taking a type name, because the
memo key is the build's own qualified name and one function answering for two
types would serve the second reader the first type's sites.

**Driven off the descriptors, not off a list of those fourteen.** A list would
be a fourth place the pin has to be remembered, and its failure is silent: a
site the list does not name is a site S031 and S032 never see, so a feed
carrying an empty `TranslatedString` there passes. Walking the schema instead
means a fifteenth site is covered the day `tools/gen_schema_current.py`
regenerates, with no rule change.

**`containers` is what makes it a walk rather than a scan of everything.** The
recursion descends only into messages that can reach a `TranslatedString`,
computed once from the current schema as a transitive closure over
message-typed fields. A message the current schema does not declare at all is
descended into anyway rather than pruned, because the alternative is to prune
exactly the case this design exists to handle: a type nobody here has seen yet.

**Presence is tested before descent.** `getHeaderText()` on an alert that names
none answers a default instance carrying zero translations, which is precisely
what S031 fires on, so a walk that read defaults would report every alert in the
feed. A field that *was* written and carries no translation is a site, and is
S031's actual finding.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.proto.descriptor import Schema
from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules._shared.memo import memoised

if TYPE_CHECKING:  # Type-only: nothing under `rules/` may import the runner at
    # run time, because it reaches the static layer and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = [
    "LOCALIZED_IMAGE",
    "TRANSLATED_IMAGE",
    "TRANSLATED_STRING",
    "LocalizedSite",
    "TranslationSite",
    "containers",
    "images",
    "localized_images",
    "translations",
]

#: The message type S031 and S032 are about. Named once so the walk, the
#: container closure and the tests all mean the same thing by it.
TRANSLATED_STRING = "TranslatedString"

#: The message type S033 and S034 are about, on the same terms.
TRANSLATED_IMAGE = "TranslatedImage"

#: The repeated field inside it, which S035 and S036 read one entry at a time.
LOCALIZED_IMAGE = "localized_image"


def containers(schema: Schema, type_name: str) -> frozenset[str]:
    """Message names that can hold a `type_name`, directly or through another.

    A transitive closure rather than one level, because the sites sit two and
    three messages deep: `FeedMessage` holds `FeedEntity` holds `Alert` holds
    the `TranslatedString`, and a walk pruning on the direct holders alone would
    stop at the entity list and find nothing at all.
    """
    holders = {
        name
        for name, desc in schema.messages.items()
        if any(field.type_name == type_name for field in desc.fields)
    }
    growing = True
    while growing:
        growing = False
        for name, desc in schema.messages.items():
            if name in holders:
                continue
            if any(field.type_name in holders for field in desc.fields):
                holders.add(name)
                growing = True
    return frozenset(holders)


#: Computed once from the current schema. A message name it does not carry is
#: not pruned; see the module docstring.
CONTAINERS = containers(SCHEMA, TRANSLATED_STRING)

#: The same closure for the image type. Separate rather than a union, because a
#: walk pruning on the union would descend into messages that can only reach the
#: other type and yield nothing from them.
IMAGE_CONTAINERS = containers(SCHEMA, TRANSLATED_IMAGE)


@dataclass(frozen=True, slots=True)
class TranslationSite:
    """One internationalised value that was written, and where.

    `translated` is the `TranslatedString` or the `TranslatedImage` itself: S031
    and S033 count what it holds and S032 and S034 count how many of those omit
    a language tag, so the path alone would answer none of the four.
    """

    path: str
    field: str
    translated: Msg


@dataclass(frozen=True, slots=True)
class LocalizedSite:
    """One `LocalizedImage` inside a `TranslatedImage`, and where it was."""

    path: str
    index: int
    image: Msg


def translations(message: Any, ctx: RuleContext) -> tuple[TranslationSite, ...]:
    """Every `TranslatedString` in `message`, walked at most once per context."""
    return memoised(_build, message, ctx)


def images(message: Any, ctx: RuleContext) -> tuple[TranslationSite, ...]:
    """Every `TranslatedImage` in `message`, walked at most once per context."""
    return memoised(_build_images, message, ctx)


def localized_images(message: Any, ctx: RuleContext) -> tuple[LocalizedSite, ...]:
    """Every `LocalizedImage` of every `TranslatedImage`, flattened.

    S035 and S036 both read one image at a time and both have to name where it
    was, so the path convention lives here rather than in two rules. A plain
    projection over the memoised walk above rather than a memo entry of its own:
    the work is one enumerate over a tuple that has already been built.
    """
    return tuple(
        LocalizedSite(f"{site.path}.{LOCALIZED_IMAGE}[{index}]", index, image)
        for site in images(message, ctx)
        for index, image in enumerate(site.translated.get(LOCALIZED_IMAGE))
    )


def _build(message: Any, ctx: RuleContext) -> tuple[TranslationSite, ...]:
    return tuple(_sites(message, "", TRANSLATED_STRING, CONTAINERS))


def _build_images(message: Any, ctx: RuleContext) -> tuple[TranslationSite, ...]:
    return tuple(_sites(message, "", TRANSLATED_IMAGE, IMAGE_CONTAINERS))


def _sites(msg: Msg, path: str, wanted: str, holders: frozenset[str]) -> Iterator[TranslationSite]:
    for field in msg.desc.fields:
        if field.kind != "message" or not msg.has(field.name):
            continue
        value = msg.get(field.name)
        items = value if field.label == "repeated" else [value]
        for index, item in enumerate(items):
            here = _join(path, field.name, index if field.label == "repeated" else None)
            if field.type_name == wanted:
                yield TranslationSite(here, field.name, item)
            elif field.type_name in holders or field.type_name not in SCHEMA.messages:
                yield from _sites(item, here, wanted, holders)


def _join(path: str, name: str, index: int | None) -> str:
    """`entity[0].alert.header_text`, built as the walk descends."""
    here = name if index is None else f"{name}[{index}]"
    return f"{path}.{here}" if path else here
