"""The internationalised-value walk, read by S031 to S036.

The claim this module makes is that it is driven off the schema
rather than off a list of the sites that exist today, so a `TranslatedString`
field added at a later pin is covered the day the schema regenerates, with no
rule change and no missed site. Two tests hold that claim rather than one:

- the walk reaches **every** `TranslatedString`-typed field the current schema
  declares, with the fixture built from the schema so the count cannot drift
  from it;
- a schema this project has never seen, carrying the field on a message that
  does not exist at this pin, is walked correctly.

The plan says there are eleven such sites. There are fourteen, and the first
test is where that number comes from rather than from counting by hand.

Cohort F added the `TranslatedImage` half, which is the same walk over a second
type for S033 to S036, plus the flattened `localized_images` view those last two
read. The tests for it are at the end of this file and hold the same claim: the
sites come from the descriptors, so the one site that exists today is not what
the walk is written against.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.decode import decode
from gtfs_rt_validator.proto.descriptor import FieldDesc, MessageDesc, Schema
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules._shared import walk_translations
from gtfs_rt_validator.rules._shared.walk_translations import (
    TRANSLATED_IMAGE,
    TRANSLATED_STRING,
    containers,
    images,
    localized_images,
    translations,
)
from specfixtures import context, entity, message, sharing

#: One well-formed `TranslatedString`. `text` is `required`, so a translation
#: without one does not decode.
TEXT = {"translation": [{"text": "Elevator out of service"}]}


def translated_fields(message_name: str) -> list[str]:
    """The `TranslatedString` fields of one message, in declaration order."""
    return [
        field.name
        for field in SCHEMA.message(message_name).fields
        if field.type_name == TRANSLATED_STRING
    ]


def test_the_containers_are_computed_from_the_schema_not_listed():
    """Which messages can hold a `TranslatedString`, directly or through another
    message. The walk prunes on this, so an answer that is too small is a site
    the rules never see."""
    assert containers(SCHEMA, TRANSLATED_STRING) == frozenset(
        {"Alert", "Stop", "FeedEntity", "FeedMessage"}
    )


def test_every_translated_string_field_the_schema_declares_is_reached():
    """The fixture is generated from the schema, so this cannot pass by naming
    the sites the walk happens to visit. Fourteen at this pin: eight on `Alert`
    and six on `Stop`."""
    alert_fields, stop_fields = translated_fields("Alert"), translated_fields("Stop")
    feed = message(
        entity("a", alert=dict.fromkeys(alert_fields, TEXT)),
        entity("b", stop=dict.fromkeys(stop_fields, TEXT)),
    )

    found = translations(feed, context())

    assert len(alert_fields) + len(stop_fields) == 14
    assert [site.path for site in found] == [
        *(f"entity[0].alert.{name}" for name in alert_fields),
        *(f"entity[1].stop.{name}" for name in stop_fields),
    ]
    assert [site.field for site in found] == [*alert_fields, *stop_fields]


def test_the_translated_string_itself_comes_back_so_the_rules_can_read_it():
    """S031 counts the translations and S032 counts the ones with no language,
    so what the walk hands over is the message, not the path alone."""
    feed = message(
        entity(
            "a",
            alert={
                "header_text": {"translation": [{"text": "one"}, {"text": "two", "language": "en"}]}
            },
        )
    )

    (site,) = translations(feed, context())

    assert [each.get("text") for each in site.translated.get("translation")] == ["one", "two"]


def test_an_absent_translated_string_is_not_a_site():
    """`getHeaderText()` on an alert that has none answers a default instance
    carrying zero translations, which is exactly what S031 fires on. A walk that
    did not test presence would report every alert in the feed."""
    feed = message(entity("a", alert={"cause": 3}), entity("b", stop={"stop_id": "A"}))

    assert translations(feed, context()) == ()


def test_a_present_but_empty_translated_string_is_a_site():
    """S031's own finding: the field was written and carries no translation."""
    feed = message(entity("a", alert={"header_text": {}}))

    (site,) = translations(feed, context())

    assert site.translated.get("translation") == []


#: A schema this project has never seen: the field on a message that does not
#: exist at the current pin, reached through a container that does.
LATER = Schema(
    messages={
        "FeedMessage": MessageDesc(
            "FeedMessage",
            (
                FieldDesc(1, "header", "message", "required", "FeedHeader"),
                FieldDesc(2, "entity", "message", "repeated", "FeedEntity"),
            ),
        ),
        "FeedHeader": MessageDesc(
            "FeedHeader", (FieldDesc(1, "gtfs_realtime_version", "string", "required", None, ""),)
        ),
        "FeedEntity": MessageDesc(
            "FeedEntity",
            (
                FieldDesc(1, "id", "string", "required", None, ""),
                FieldDesc(2, "kiosk", "message", "optional", "Kiosk"),
            ),
        ),
        "Kiosk": MessageDesc(
            "Kiosk", (FieldDesc(1, "caption", "message", "optional", "TranslatedString"),)
        ),
        "TranslatedString": MessageDesc(
            "TranslatedString",
            (FieldDesc(1, "translation", "message", "repeated", "TranslatedString.Translation"),),
        ),
        "TranslatedString.Translation": MessageDesc(
            "TranslatedString.Translation",
            (
                FieldDesc(1, "text", "string", "required", None, ""),
                FieldDesc(2, "language", "string", "optional", None, ""),
            ),
        ),
    },
    enums={},
)


def test_a_site_that_does_not_exist_at_this_pin_is_still_walked():
    """The whole reason this is a schema walk. A hand-written list of the
    fourteen sites would go on being a list of fourteen, and the fifteenth would
    be invisible to S031 and S032 until somebody remembered to add it."""
    assert containers(LATER, TRANSLATED_STRING) == frozenset({"Kiosk", "FeedEntity", "FeedMessage"})

    feed = decode(
        encode(
            {
                "header": {"gtfs_realtime_version": "2.0"},
                "entity": [{"id": "a", "kiosk": {"caption": TEXT}}],
            },
            LATER,
        ),
        LATER,
    )

    (site,) = translations(feed, context())

    assert (site.path, site.field) == ("entity[0].kiosk.caption", "caption")


def test_two_rules_sharing_one_context_walk_the_translations_once(monkeypatch):
    """S031 and S032 read one message between them."""
    runs = sharing(monkeypatch, walk_translations, "_build")
    feed = message(entity("a", alert={"header_text": TEXT, "description_text": TEXT}))
    ctx = context()

    assert len(translations(feed, ctx)) == 2
    assert [site.field for site in translations(feed, ctx)] == ["header_text", "description_text"]

    assert runs == [feed]


#: One well-formed `LocalizedImage`. `url` and `media_type` are `required`.
IMAGE = {"url": "https://example.com/detour.png", "media_type": "image/png"}


def test_the_image_containers_are_computed_from_the_schema_too():
    """`TranslatedImage` sits on `Alert.image` alone at this pin, so the closure
    is the three messages that reach it."""
    assert containers(SCHEMA, TRANSLATED_IMAGE) == frozenset({"Alert", "FeedEntity", "FeedMessage"})


def test_every_translated_image_field_the_schema_declares_is_reached():
    image_fields = [
        field.name
        for field in SCHEMA.message("Alert").fields
        if field.type_name == TRANSLATED_IMAGE
    ]
    written = {name: {"localized_image": [IMAGE]} for name in image_fields}
    feed = message(entity("a", alert=written))

    found = images(feed, context())

    assert image_fields == ["image"]
    assert [site.path for site in found] == ["entity[0].alert.image"]


def test_the_two_walks_do_not_answer_each_others_sites():
    """A union closure would have descended into messages that can reach only
    the other type, and a shared memo entry would have served the first caller's
    sites to the second."""
    feed = message(entity("a", alert={"header_text": TEXT, "image": {"localized_image": [IMAGE]}}))
    ctx = context()

    assert [site.field for site in translations(feed, ctx)] == ["header_text"]
    assert [site.field for site in images(feed, ctx)] == ["image"]


def test_the_localized_images_view_flattens_and_numbers_them():
    """S035 and S036 read one image at a time and both name where it was, so the
    path convention is here rather than in two rule modules."""
    second = {"url": "https://example.com/b.png", "media_type": "image/svg+xml"}
    feed = message(entity("a", alert={"image": {"localized_image": [IMAGE, second]}}))

    found = localized_images(feed, context())

    assert [(site.path, site.index) for site in found] == [
        ("entity[0].alert.image.localized_image[0]", 0),
        ("entity[0].alert.image.localized_image[1]", 1),
    ]
    assert [site.image.get("media_type") for site in found] == ["image/png", "image/svg+xml"]


def test_two_rules_sharing_one_context_walk_the_images_once(monkeypatch):
    """S033 to S036 read one message between them, and the flattened view is a
    projection over the same memo entry rather than a second walk."""
    runs = sharing(monkeypatch, walk_translations, "_build_images")
    feed = message(entity("a", alert={"image": {"localized_image": [IMAGE]}}))
    ctx = context()

    assert len(images(feed, ctx)) == 1
    assert len(localized_images(feed, ctx)) == 1
    assert len(localized_images(feed, ctx)) == 1

    assert runs == [feed]
