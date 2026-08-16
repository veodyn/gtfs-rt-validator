"""S031: a `TranslatedString` that was written and says nothing.

The rule is about the type rather than about any field, so the interesting test
is that it reaches a site nobody named: the fixture below writes the field on
`Stop`, which upstream cannot see at all, and the walk finds it because it is
driven off the schema.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s031 import check
from specfixtures import context, entity, message

TEXT = {"translation": [{"text": "Elevator out of service"}]}


def found(*entities):
    return list(check(message(*entities), context()) or ())


def prefixes(*entities):
    return [occurrence.prefix for occurrence in found(*entities)]


def test_an_empty_translated_string_reports():
    assert prefixes(entity("a0", alert={"header_text": {}})) == [
        "entity[0].alert.header_text was written with no translation"
    ]


def test_a_translated_string_with_one_translation_is_silent():
    """The satisfying fixture."""
    assert prefixes(entity("a0", alert={"header_text": TEXT})) == []


def test_an_absent_translated_string_is_not_a_site():
    """The getter answers a default instance carrying zero translations, so a
    rule that read defaults would report every alert in the feed."""
    assert prefixes(entity("a0", alert={"cause": 3})) == []


def test_the_occurrence_locates_the_field():
    (occurrence,) = found(entity("a0", alert={"description_text": {}}))

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].alert.description_text"


def test_every_empty_site_reports_once():
    alert = {"header_text": {}, "description_text": TEXT, "url": {}}

    assert prefixes(entity("a0", alert=alert)) == [
        "entity[0].alert.url was written with no translation",
        "entity[0].alert.header_text was written with no translation",
    ]


def test_a_site_on_a_message_upstream_cannot_see_is_reached():
    """`Stop` is post-2015 and carries six `TranslatedString` fields. The rule
    names none of them; the walk finds them from the descriptors."""
    assert prefixes(entity("a0", stop={"stop_id": "S1", "stop_name": {}})) == [
        "entity[0].stop.stop_name was written with no translation"
    ]
