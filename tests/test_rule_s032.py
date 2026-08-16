"""S032: two translations of one string with no language tag between them.

The untagged translation is the resolution procedure's last resort, so a second
one is unreachable and a consumer's choice between them is arbitrary. One is
allowed and is the ordinary case for a feed that does no i18n at all, which is
why the boundary at exactly one is tested here.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s032 import check
from specfixtures import context, entity, message


def translated(*translations):
    return {"translation": [dict(each) for each in translations]}


def found(**alert):
    return list(check(message(entity("a0", alert=dict(alert))), context()) or ())


def prefixes(**alert):
    return [occurrence.prefix for occurrence in found(**alert)]


def test_two_untagged_translations_report():
    header = translated({"text": "one"}, {"text": "two"})

    assert prefixes(header_text=header) == [
        "entity[0].alert.header_text has 2 translations with no language tag"
    ]


def test_exactly_one_untagged_translation_is_allowed():
    """The boundary, and the ordinary case for a feed that does no i18n."""
    header = translated({"text": "one"}, {"text": "two", "language": "fr"})

    assert prefixes(header_text=header) == []


def test_no_untagged_translation_at_all_is_allowed():
    """The satisfying fixture for a fully translated feed."""
    header = translated({"text": "one", "language": "en"}, {"text": "two", "language": "fr"})

    assert prefixes(header_text=header) == []


def test_an_empty_language_tag_is_a_specified_one():
    """The clause is about an *unspecified* tag, and a producer that wrote the
    field wrote it. Presence is how the rest of the tier reads proto2 too."""
    header = translated({"text": "one", "language": ""}, {"text": "two"})

    assert prefixes(header_text=header) == []


def test_three_untagged_translations_still_report_once():
    """One occurrence per string. The defect is the string's, not each
    translation's, and the count says how bad it is."""
    header = translated({"text": "one"}, {"text": "two"}, {"text": "three"})

    assert prefixes(header_text=header) == [
        "entity[0].alert.header_text has 3 translations with no language tag"
    ]


def test_the_occurrence_locates_the_field():
    (occurrence,) = found(description_text=translated({"text": "one"}, {"text": "two"}))

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].alert.description_text"


def test_an_empty_translated_string_is_not_this_rules_finding():
    """Zero untagged translations is not more than one. S031 has that feed."""
    assert prefixes(header_text={}) == []
