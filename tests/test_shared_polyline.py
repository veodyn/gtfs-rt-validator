"""The encoded-polyline decoder, read by S040 and by P015.

**The expectations are pinned to somebody else's document, not computed here.**
Both vectors below are the worked examples published in Google's Encoded
Polyline Algorithm Format at
https://developers.google.com/maps/documentation/utilities/polylinealgorithm,
read on 2026-08-15:

- the three-point example, `(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)`
  encoding to ``_p~iF~ps|U_ulLnnqC_mqNvxq`@``;
- the single-value example, `-179.9832104`, which the document carries through
  "multiply by 1e5 and round" to `-17998321` and then to `~oia@`.

A vector computed by running this decoder and writing down what it said would
be a test that the decoder does what it does. The document is the only thing
here that can disagree with it.

The second vector is lossy in the direction that matters: the format keeps five
decimal places, so `-179.9832104` comes back as `-179.98321`, which is the
document's own intermediate value divided by 1e5 rather than a rounding this
project chose.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.rules._shared import polyline as polyline_module
from gtfs_rt_validator.rules._shared.polyline import decode_polyline, polyline
from specfixtures import context, sharing

#: Google's three-point worked example, encoded then expected.
GOOGLE_EXAMPLE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
GOOGLE_POINTS = ((38.5, -120.2), (40.7, -120.95), (43.252, -126.453))

#: Google's single-value worked example, used twice to make one point. The
#: leading backtick is part of the encoding, not markdown: the document renders
#: the string inside code quotes and it is six characters, not five.
SINGLE_VALUE = "`~oia@"


def test_googles_three_point_example_decodes_to_googles_three_points():
    decoded = decode_polyline(GOOGLE_EXAMPLE)

    assert decoded.points == GOOGLE_POINTS
    assert decoded.error is None


def test_googles_single_value_example_decodes_to_its_own_intermediate_value():
    """`-17998321` divided by 1e5, which is what the document's own worked
    steps say the encoded chunk carries."""
    decoded = decode_polyline(SINGLE_VALUE + SINGLE_VALUE)

    assert decoded.points == ((-179.98321, -179.98321),)
    assert decoded.error is None


def test_an_empty_polyline_decodes_to_no_points_and_is_not_an_error():
    """An absent `encoded_polyline` is S039's finding and a short one is S040's.
    Neither is a decode failure, and reporting one here would give S040 two
    reasons to fire on one field."""
    decoded = decode_polyline("")

    assert decoded.points == ()
    assert decoded.error is None


def test_a_latitude_with_no_longitude_does_not_decode():
    """Points come in pairs, so a trailing half-pair is a broken string rather
    than a point at longitude zero."""
    decoded = decode_polyline("_p~iF")

    assert decoded.points == ()
    assert decoded.error is not None


def test_a_chunk_that_never_terminates_does_not_decode():
    """Every chunk but the last carries the continuation bit, so a string whose
    final character still carries it ended in the middle of a number."""
    decoded = decode_polyline("_p~iF~ps|")

    assert decoded.error is not None


def test_a_character_outside_the_encodings_range_does_not_decode():
    """The format adds 63 to every five-bit group, so nothing below `?` can
    appear in a well-formed string."""
    decoded = decode_polyline("_p~iF ")

    assert decoded.error is not None


def test_what_decoded_before_the_failure_is_kept():
    """A feed is expected to be malformed, and a rule reporting "did not decode"
    is more useful when it can say how far it got. Notices are data: a broken
    polyline is a finding, never an exception."""
    decoded = decode_polyline(GOOGLE_EXAMPLE + "_p~iF")

    assert decoded.points == GOOGLE_POINTS
    assert decoded.error is not None


def test_two_rules_decoding_one_polyline_in_one_context_decode_it_once(monkeypatch):
    """S040 counts the points and P015 measures them, and the decode is the
    expensive half of both."""
    runs = sharing(monkeypatch, polyline_module, "_build")
    ctx = context()

    assert polyline(GOOGLE_EXAMPLE, ctx).points == GOOGLE_POINTS
    assert polyline(GOOGLE_EXAMPLE, ctx).points == GOOGLE_POINTS

    assert runs == [GOOGLE_EXAMPLE]


def test_two_polylines_in_one_message_are_memoised_apart(monkeypatch):
    """A feed may carry many `Shape` entities, so the memo entry is per encoded
    string. Keyed on the module alone, the second shape would be handed the
    first one's points."""
    runs = sharing(monkeypatch, polyline_module, "_build")
    ctx = context()

    assert polyline(GOOGLE_EXAMPLE, ctx).points == GOOGLE_POINTS
    assert polyline(SINGLE_VALUE * 2, ctx).points == ((-179.98321, -179.98321),)
    assert polyline(GOOGLE_EXAMPLE, ctx).points == GOOGLE_POINTS

    assert runs == [GOOGLE_EXAMPLE, SINGLE_VALUE * 2]


@pytest.mark.parametrize(
    "character",
    [chr(127), chr(128), chr(0x2028), "ÿ"],
)
def test_a_character_above_the_encoding_range_is_refused(character):
    """The upper bound, which the lower-bound-only check let through.

    Google's format adds 63 to a six-bit value, so a valid encoded character is
    ASCII 63 to 126, `?` through `~`. The decoder checked `group < 0` and nothing
    else, and `group & 0x1f` then quietly discarded the high bits.

    The audit's reproduction is the damaging shape: `(chr(127) + "?") * 2`
    decoded as a clean two-point polyline at the origin with no error, which is
    exactly what a rule asking "does this shape have at least two points?" is
    looking for. Malformed input passing as valid geometry is worse than
    malformed input being rejected, so this is an error rather than a truncation.

    Reverting the bound turns this test red and no other, which is why it is here
    rather than folded into an existing case.
    """
    decoded = decode_polyline((character + "?") * 2)
    assert decoded.error is not None
    assert repr(character)[1:-1] in decoded.error or character in decoded.error
    assert decoded.points == ()


def test_the_boundary_characters_themselves_are_accepted():
    """`?` is 0 and `~` is 63, so both ends of the range must still decode.

    A bound written as `<` instead of `<=` would pass the test above while
    breaking every real polyline that uses the top of the range.
    """
    assert decode_polyline("??").points == ((0.0, 0.0),)
    assert decode_polyline(GOOGLE_EXAMPLE).error is None
