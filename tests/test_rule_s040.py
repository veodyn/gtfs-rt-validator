"""S040: an encoded_polyline that is too short, or that does not decode.

The three-point string below is the worked example published in Google's
Encoded Polyline Algorithm Format, which `_shared/polyline.py` is tested
against; the single-point string is its first coordinate pair alone. Both are
external expectations rather than values computed here to make a test pass.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s040 import check
from specfixtures import context, entity, message

#: (38.5, -120.2), (40.7, -120.95), (43.252, -126.453).
THREE_POINTS = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"

#: The first of those three on its own.
ONE_POINT = "_p~iF~ps|U"


def found(*polylines):
    feed = message(
        *(
            entity(f"s{index}", shape={"shape_id": f"RT{index}", "encoded_polyline": each})
            for index, each in enumerate(polylines)
        )
    )
    return list(check(feed, context()) or ())


def prefixes(*polylines):
    return [occurrence.prefix for occurrence in found(*polylines)]


def test_a_polyline_with_two_or_more_points_is_silent():
    """The satisfying fixture."""
    assert prefixes(THREE_POINTS) == []


def test_a_single_point_reports():
    assert prefixes(ONE_POINT) == [
        "entity ID s0 encoded_polyline decodes to 1 point, and at least two are required"
    ]


def test_an_empty_polyline_decodes_to_nothing_and_reports():
    """`encoded_polyline` written as the empty string is present, so S039 is
    silent on it and this is where the feed is reported."""
    assert prefixes("") == [
        "entity ID s0 encoded_polyline decodes to 0 points, and at least two are required"
    ]


def test_a_polyline_that_does_not_decode_reports_why():
    """A character outside the encoding. The decoder answers a `Polyline` with
    an error rather than raising, because a malformed feed is data."""
    assert prefixes("_p~iF~ps|U\x01") == [
        (
            "entity ID s0 encoded_polyline does not decode: character '\\x01' is not part of "
            "the encoding"
        )
    ]


def test_a_truncated_value_reports_why():
    """A value whose continuation bit is set on the last character."""
    (prefix,) = prefixes("_p~iF~ps|U_")

    assert prefix.startswith("entity ID s0 encoded_polyline does not decode: ")


def test_a_latitude_with_no_longitude_after_it_reports():
    (prefix,) = prefixes("_p~iF~ps|U_ulL")

    assert prefix == (
        "entity ID s0 encoded_polyline does not decode: a latitude with no longitude after it"
    )


def test_the_occurrence_locates_the_shape():
    (occurrence,) = found(THREE_POINTS, ONE_POINT)

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[1].shape"


def test_a_shape_with_no_polyline_is_out_of_scope():
    """S039's finding. There is nothing here to decode."""
    feed = message(entity("s0", shape={"shape_id": "RT0"}))

    assert list(check(feed, context()) or ()) == []


def test_each_offending_shape_reports_once():
    assert len(prefixes(ONE_POINT, THREE_POINTS, "")) == 2
