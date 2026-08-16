"""S033: a `TranslatedImage` that was written and carries no image.

The same shape as S031 on the other internationalised type, and it goes through
the same schema-driven walk. `TranslatedImage` sits on one field at this pin,
which is exactly the case a hand-written list would look adequate for.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s033 import check
from specfixtures import context, entity, message

#: `url` and `media_type` are `required`, so a localized image without both does
#: not decode and cannot be a fixture.
IMAGE = {"url": "https://example.com/detour.png", "media_type": "image/png"}


def found(**alert):
    return list(check(message(entity("a0", alert=dict(alert))), context()) or ())


def prefixes(**alert):
    return [occurrence.prefix for occurrence in found(**alert)]


def test_an_empty_translated_image_reports():
    assert prefixes(image={}) == ["entity[0].alert.image was written with no localized image"]


def test_a_translated_image_with_one_image_is_silent():
    """The satisfying fixture."""
    assert prefixes(image={"localized_image": [IMAGE]}) == []


def test_an_absent_translated_image_is_not_a_site():
    """The getter answers a default instance holding zero images, so a rule that
    read defaults would report every alert in the feed."""
    assert prefixes(cause=3) == []


def test_the_occurrence_locates_the_field():
    (occurrence,) = found(image={})

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].alert.image"


def test_a_translated_string_is_not_a_translated_image():
    """The two walks are separate, so S031's finding is not also S033's."""
    assert prefixes(header_text={}) == []
