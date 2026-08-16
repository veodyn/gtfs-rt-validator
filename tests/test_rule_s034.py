"""S034: two localized images of one `TranslatedImage` with no language tag.

The clause is the same sentence S032 cites, restated on `LocalizedImage` at a
different line. Two rules, because they are two clauses about two messages: the
citation gate resolves a quote to the clause that owns it, and one module could
only ever quote one of the two.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s034 import check
from specfixtures import context, entity, message


def localized(*images):
    return {"localized_image": [{"media_type": "image/png", **each} for each in images]}


def found(**alert):
    return list(check(message(entity("a0", alert=dict(alert))), context()) or ())


def prefixes(**alert):
    return [occurrence.prefix for occurrence in found(**alert)]


def test_two_untagged_images_report():
    image = localized({"url": "https://example.com/a.png"}, {"url": "https://example.com/b.png"})

    assert prefixes(image=image) == [
        "entity[0].alert.image has 2 localized images with no language tag"
    ]


def test_exactly_one_untagged_image_is_allowed():
    """The boundary."""
    image = localized(
        {"url": "https://example.com/a.png"},
        {"url": "https://example.com/b.png", "language": "fr"},
    )

    assert prefixes(image=image) == []


def test_no_untagged_image_at_all_is_allowed():
    """The satisfying fixture."""
    image = localized(
        {"url": "https://example.com/a.png", "language": "en"},
        {"url": "https://example.com/b.png", "language": "fr"},
    )

    assert prefixes(image=image) == []


def test_the_occurrence_locates_the_field():
    image = localized({"url": "https://example.com/a.png"}, {"url": "https://example.com/b.png"})

    (occurrence,) = found(image=image)

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].alert.image"


def test_an_empty_translated_image_is_not_this_rules_finding():
    """Zero untagged images is not more than one. S033 has that feed."""
    assert prefixes(image={}) == []


def test_untagged_translations_of_a_string_are_not_counted_here():
    """The two walks are separate and so are the two clauses."""
    assert prefixes(header_text={"translation": [{"text": "one"}, {"text": "two"}]}) == []
