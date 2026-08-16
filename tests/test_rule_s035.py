"""S035: a localized image whose media_type is not an image type.

`media_type` is `required`, so every LocalizedImage that decodes has one and the
rule never has to reason about absence. The comparison is a prefix, which is
what the clause says: `image/svg+xml` is as acceptable as `image/png`.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s035 import check
from specfixtures import context, entity, message

URL = "https://example.com/detour.png"


def found(*media_types):
    alert = {"image": {"localized_image": [{"url": URL, "media_type": t} for t in media_types]}}
    return list(check(message(entity("a0", alert=alert)), context()) or ())


def prefixes(*media_types):
    return [occurrence.prefix for occurrence in found(*media_types)]


def test_a_media_type_that_is_not_an_image_reports():
    assert prefixes("text/html") == [
        (
            'entity[0].alert.image.localized_image[0] media_type "text/html" '
            'does not start with "image/"'
        )
    ]


def test_an_image_media_type_is_silent():
    """The satisfying fixture."""
    assert prefixes("image/png") == []


def test_any_image_subtype_is_accepted():
    """The clause constrains the prefix and nothing else, so a subtype nobody
    has heard of is not this rule's business."""
    assert prefixes("image/svg+xml", "image/avif", "image/x-not-real") == []


def test_a_case_variant_of_the_prefix_is_still_an_image_type():
    """The cited sentence's subject is "The type", whose only antecedent is
    "IANA media type" on the line above it, `:1067`, which the clause index
    records as this clause's `unit_line`. RFC 6838 section 4.2: "Both top-level
    type and subtype names are case-insensitive." So a producer that shouts the
    type has still named the same media type, and reporting it would be this
    rule deciding something the sentence does not."""
    assert prefixes("IMAGE/PNG", "Image/png", "image/PNG") == []


def test_a_case_variant_of_a_type_outside_the_tree_still_reports():
    """Folding case widens what passes and nothing else."""
    assert len(prefixes("TEXT/HTML")) == 1


def test_a_type_that_merely_contains_image_is_not_a_prefix():
    assert len(prefixes("application/image")) == 1


def test_the_occurrence_locates_the_image():
    (occurrence,) = found("image/png", "text/html")

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].alert.image.localized_image[1]"


def test_each_offending_image_reports_once():
    assert len(prefixes("text/html", "image/png", "video/mp4")) == 2


def test_a_translated_image_with_no_localized_images_is_silent():
    """S033's feed, not this one."""
    assert list(check(message(entity("a0", alert={"image": {}})), context()) or ()) == []
