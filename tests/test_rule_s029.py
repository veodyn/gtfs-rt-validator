"""S029, the one rule in the tier deliberately narrower than its clause.

"The information in the description should add to the information of the header"
is not decidable in general. Equality is the one case where it provably adds
none, so the rule enforces a strict subset and says so. These tests pin the
subset: identical translations report, and anything that differs at all does not,
however little it differs by.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s029 import check
from specfixtures import context, entity, message

ONE = {"translation": [{"text": "Elevator out of service", "language": "en"}]}


def found(**alert):
    feed = message(entity("a0", alert=dict(alert)))
    return list(check(feed, context()) or ())


def prefixes(**alert):
    return [occurrence.prefix for occurrence in found(**alert)]


def test_a_description_identical_to_the_header_reports():
    assert prefixes(header_text=ONE, description_text=ONE) == [
        "alert ID a0 description_text repeats header_text and adds nothing to it"
    ]


def test_a_description_that_differs_by_one_character_is_silent():
    """The satisfying fixture. The rule enforces equality and nothing weaker,
    so anything a producer actually wrote differently passes."""
    other = {"translation": [{"text": "Elevator out of service.", "language": "en"}]}

    assert prefixes(header_text=ONE, description_text=other) == []


def test_a_different_language_tag_on_the_same_text_is_not_equality():
    """The language is part of what a translation says, so two translations with
    one text and two tags are two different strings to two different readers."""
    other = {"translation": [{"text": "Elevator out of service", "language": "fr"}]}

    assert prefixes(header_text=ONE, description_text=other) == []


def test_an_omitted_language_differs_from_a_present_one():
    other = {"translation": [{"text": "Elevator out of service"}]}

    assert prefixes(header_text=ONE, description_text=other) == []


def test_the_order_of_the_translations_matters():
    """Resolution picks the first matching translation, so two orders resolve
    differently for a reader whose language matches neither exactly."""
    first = {"translation": [{"text": "a", "language": "en"}, {"text": "b", "language": "fr"}]}
    second = {"translation": [{"text": "b", "language": "fr"}, {"text": "a", "language": "en"}]}

    assert prefixes(header_text=first, description_text=second) == []


def test_identical_multi_language_strings_report():
    both = {"translation": [{"text": "a", "language": "en"}, {"text": "b", "language": "fr"}]}

    assert len(prefixes(header_text=both, description_text=both)) == 1


def test_an_alert_with_only_one_of_the_two_is_silent():
    assert prefixes(header_text=ONE) == []
    assert prefixes(description_text=ONE) == []


def test_two_empty_translated_strings_are_not_reported_here():
    """Both fields written and both carrying nothing is S031's finding, twice.
    Reporting it a third time as "the description adds nothing" would say the
    same thing about the same alert in a third way."""
    assert prefixes(header_text={}, description_text={}) == []


def test_the_occurrence_locates_the_alert():
    (occurrence,) = found(header_text=ONE, description_text=ONE)

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].alert"


def test_the_text_to_speech_fields_are_not_this_clause():
    """`tts_description_text` is by definition the same information as
    `description_text`, said differently, and the clause is about the pair the
    sentence names."""
    assert prefixes(tts_header_text=ONE, tts_description_text=ONE) == []
