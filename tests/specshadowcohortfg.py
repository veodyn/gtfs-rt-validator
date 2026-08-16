"""Cohort F and G's jar fixtures: translations, localized images, and shapes.

Split out of `specshadowfeeds.py` for the reason that file was split out of
`specshadow.py`, so neither grows past the size hook, and the way
`practiceshadowcohortf.py` and `practiceshadowcohortde.py` do for the practice
tier. Same contract: every `jar_ids` set here was **recorded from a real jar
run** rather than predicted. All thirteen are empty, and none of the ten rules
declares an upstream overlap, so every `not_emitted` is `None`.

**Two strengths of evidence live in this file and they are not the same claim.**
An empty `jar_ids` means one of two very different things:

1. **The jar decoded the defect and had nothing to say about it.** That is the
   strong form, and only S031 and S032 have it. `TranslatedString` predates the
   2015 pin: `Alert.header_text` is field 10 in both schemas,
   `TranslatedString.translation` is field 1 in both, and
   `Translation.text` and `.language` are 1 and 2 in both. So protobuf-java
   parsed a header text carrying zero translations, and one carrying two
   untagged ones, into typed fields the 56 could have read, and none of them
   did.
2. **The jar could not decode the message the defect sits on.** That is the weak
   form and it is all S033 to S040 get. `Alert.image` is field 15 and
   `FeedEntity.shape` is field 6; the 2015 schema declares neither, so
   `TranslatedImage`, `LocalizedImage` and `Shape` land whole in the unknown
   field set and the jar never sees a `media_type`, a URL or a polyline at all.
   An upstream rule cannot report what its bindings dropped, so silence here is
   consistent with each rule's declared overlap and is not evidence for it. What
   settles those eight is reading the Java, which is where the declaration in
   `OVERLAP` came from; this file only records that the jar was asked.

The shape entities are also invisible to S001, which is why they are single
entities rather than a shape beside a clean trip update: `shape` is a payload
field of `FeedEntity` under the current schema, so an entity carrying one and
nothing else carries exactly one payload. To the jar the same entity is an id
with an unknown field beside it, which `specshadowfeeds`'s S001 fixture already
measured to draw nothing.
"""

from __future__ import annotations

from p015fixtures import encode_polyline
from specshadow import Fixture

__all__ = ["COHORT_FG_FIXTURES"]

#: A stop on `minimal_tables()`'s route, so an alert has something to inform
#: about. `specshadow.CLEAN_ALERT` is this selector and was measured clean; the
#: fixtures below reuse the shape rather than the constant because each adds one
#: field to it.
INFORMED = [{"route_id": "R1"}]

#: A URL that satisfies S036, so that S033, S034 and S035 carry no second defect.
URL = "https://example.com/detour.png"

#: A media type that satisfies S035, on the same terms.
PNG = "image/png"

#: Three points, from Google's own worked example of the encoding. Long enough
#: that S040 is silent, so S037 and S038 are alone on their feeds.
THREE_POINTS = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"

#: One point, which is S040's short case. A location rather than a path.
ONE_POINT = encode_polyline([(27.95, -82.45)])

#: `THREE_POINTS`'s first point followed by a character the encoding has no
#: value for, which is S040's other case: `_shared/polyline.py` answers one
#: point and the reason it stopped rather than raising, so a deliberately broken
#: polyline is a finding and never a `DecodeError`.
BROKEN_POLYLINE = "_p~iF~ps|U!!!"

#: The id `minimal_tables()` writes into `shapes.txt`, which is what S038
#: forbids a realtime `Shape` from claiming.
STATIC_SHAPE_ID = "SH1"

#: An id no static table defines, for the fixtures that must not trip S038.
REALTIME_SHAPE_ID = "RT1"


def alert(**rest: object) -> list[dict[str, object]]:
    """One entity carrying an alert over R1, plus whatever the fixture adds."""
    return [{"id": "a", "alert": {"informed_entity": INFORMED, **rest}}]


def imaged(*localized: dict[str, object]) -> list[dict[str, object]]:
    """The same alert, carrying a `TranslatedImage` of these localized images."""
    return alert(image={"localized_image": list(localized)})


def localized(url: str = URL, media_type: str = PNG, **rest: object) -> dict[str, object]:
    """One `LocalizedImage`. Both named fields are `required` in the proto."""
    return {"url": url, "media_type": media_type, **rest}


def shaped(**fields: object) -> list[dict[str, object]]:
    """One entity whose only payload is a `Shape` carrying these fields."""
    return [{"id": "s0", "shape": fields}]


TRANSLATION_FIXTURES: tuple[Fixture, ...] = (
    Fixture(
        "S031",
        alert(header_text={}),
        note="a header_text that was written and holds nothing. The strong form: "
        "Alert.header_text is field 10 and TranslatedString.translation field 1 in both "
        "schemas, so the jar decoded an empty TranslatedString and said nothing",
    ),
    Fixture(
        "S032",
        alert(header_text={"translation": [{"text": "One"}, {"text": "Uno"}]}),
        note="two translations, neither carrying a language tag, so the resolution "
        "procedure's last resort is reached twice. The strong form again: Translation.text "
        "and .language are fields 1 and 2 in both schemas and the jar read both translations",
    ),
    Fixture(
        "S033",
        alert(image={}),
        note="an Alert.image that was written and holds no localized image. Alert.image is "
        "field 15, which the 2015 schema does not declare, so the jar filed the whole "
        "TranslatedImage as an unknown field: it could not have reported this",
    ),
    Fixture(
        "S034",
        imaged(localized(), localized(url=URL + "?2")),
        note="two localized images, neither carrying a language tag. Same unknown field 15, "
        "so the jar's silence is about its bindings rather than about its rules",
    ),
    Fixture(
        "S035",
        imaged(localized(media_type="text/html")),
        note="a media_type outside the image/ tree. Case is folded before the prefix test "
        "since RFC 6838 makes an IANA media type's names case-insensitive, so the fixture "
        "states a type that is wrong in any case rather than one that is merely shouted",
    ),
    Fixture(
        "S036",
        imaged(localized(url="ftp://example.com/detour.png")),
        note="the scheme half of the clause: not http:// or https://. The comparison folds "
        "case, so a fixture of HTTPS:// would be silent and this one names a third scheme",
    ),
    Fixture(
        "S036",
        imaged(localized(url="https://example.com/detour image.png")),
        note="the escaping half the audit pass added: a literal space, which RFC 3986 lets "
        "no URI carry, so it is a special character that was not escaped and is decidable "
        "from the bytes. The reserved-character half stays rejected, which is why the "
        "clause is recorded as rule_in_part",
    ),
)

SHAPE_FIXTURES: tuple[Fixture, ...] = (
    Fixture(
        "S037",
        shaped(encoded_polyline=THREE_POINTS),
        note="a Shape nothing can reference, since shape_id is the entity's name and not "
        "FeedEntity.id. FeedEntity.shape is field 6 and the 2015 schema stops at 5, so to "
        "the jar this entity is an id with an unknown field after it",
    ),
    Fixture(
        "S038",
        shaped(shape_id=STATIC_SHAPE_ID, encoded_polyline=THREE_POINTS),
        note="a realtime Shape claiming shapes.txt's own SH1, over the four shape points "
        "minimal_tables() writes",
    ),
    Fixture(
        "S038",
        shaped(shape_id=STATIC_SHAPE_ID, encoded_polyline=THREE_POINTS),
        shape_points=3,
        note="the same collision over a shapes.txt of three points, which is the case an "
        "audit pass found silent. `_tables.py:74` empties `shape_points` below "
        "`GtfsMetadata.java:127`'s feed-wide gate, so the rule now reads "
        "`StaticContext.shape_ids`, built before it. This is that fix end to end, through "
        "a real archive rather than a hand-built context",
    ),
    Fixture(
        "S039",
        shaped(shape_id=REALTIME_SHAPE_ID),
        note="a Shape with a name and no path. The id is one shapes.txt does not define, so "
        "S038 is silent and this feed carries one defect",
    ),
    Fixture(
        "S040",
        shaped(shape_id=REALTIME_SHAPE_ID, encoded_polyline=ONE_POINT),
        note="a polyline that decodes cleanly to a single point, which is a location and "
        "not a path. Present, so S039 is silent",
    ),
    Fixture(
        "S040",
        shaped(shape_id=REALTIME_SHAPE_ID, encoded_polyline=BROKEN_POLYLINE),
        note="a polyline that stops at a character the encoding has no value for. The "
        "decoder answers the one point it read plus the reason, so this is an occurrence "
        "and not an exception",
    ),
)

COHORT_FG_FIXTURES: tuple[Fixture, ...] = TRANSLATION_FIXTURES + SHAPE_FIXTURES
