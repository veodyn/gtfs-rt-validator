"""`GtfsUtils.isValidVersion` and `isV2orHigher`, pinned to Java's own parser.

Three assertions here are upstream's own, ported verbatim from
`gtfs-realtime-validator-lib/src/test/.../UtilTest.java:337-349`
(`testIsV2orHigher`): `"1.0"` is not v2, `"2.0"` and `"3.0"` are. Upstream has no
test for `isValidVersion` at all, and none for the throwing path, so everything
else below is ours.

`PARSE_ORACLE` is measured, not reasoned. Every row is what
`Float.parseFloat(s) >= 2.0f` printed on the JDK 17 this repository's jar build
already uses. Reproduce a row with::

    echo 'String s = "2.0f"; try { System.out.println(Float.parseFloat(s) >= 2.0f); }
          catch (NumberFormatException e) { System.out.println("throws"); }' | jshell -q -

The rows exist because `Float.parseFloat` and Python's `float()` accept
different strings in both directions, and a naive port would answer differently
on a feed carrying any of them: Java takes a trailing `f`/`d` suffix, hex
floats, and a leading control character, all of which Python rejects; Python
takes `inf`, `nan`, digit underscores and a non-breaking space, all of which
Java rejects. The last group is float32 rounding: `1.99999999` is below 2.0 as a
double and exactly 2.0 as a float.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.rules._shared.versions import is_v2_or_higher, is_valid_version

#: A row whose expectation is "Java threw `NumberFormatException` here".
RAISES = "throws"

PARSE_ORACLE: tuple[tuple[str, object], ...] = (
    # Upstream's own three, from UtilTest.testIsV2orHigher.
    ("1.0", False),
    ("2.0", True),
    ("3.0", True),
    # The throwing path both call sites catch, and disagree about.
    ("", RAISES),
    ("  ", RAISES),
    ("abc", RAISES),
    ("1,0", RAISES),
    ("1.0.0", RAISES),
    ("1e", RAISES),
    ("e5", RAISES),
    (".", RAISES),
    ("2.0 f", RAISES),
    # Java accepts, Python's float() does not.
    ("2.0f", True),
    ("2.0F", True),
    ("2.0d", True),
    ("2.0e0f", True),
    ("1d", False),
    ("1D", False),
    ("1f", False),
    ("0x1p3", True),
    ("0x1.8p1", True),
    ("0x2p0f", True),
    ("\x011.0", False),
    ("\x1f1.0\x00", False),
    # Python's float() accepts, Java does not.
    ("inf", RAISES),
    ("INF", RAISES),
    ("nan", RAISES),
    ("NAN", RAISES),
    ("1_0", RAISES),
    ("\xa01.0", RAISES),
    ("1.0\xa0", RAISES),
    ("1.0\u2029", RAISES),
    ("0x1.8", RAISES),
    ("Infinityf", RAISES),
    # Non-ASCII decimal digits, which Python's `\d` and `int()` both take and
    # `Float.parseFloat` does not: it reads the string through
    # `Character.digit(c, 10)` only after `FloatingDecimal.readJavaFormatString`
    # has rejected every byte outside `0` to `9`. Five scripts, in every
    # position a digit can occupy.
    ("\u0662.\u0660", RAISES),  # Arabic-Indic, the report's own example
    ("\u0968.\u0966", RAISES),  # Devanagari
    ("\uff12.\uff10", RAISES),  # fullwidth
    ("\u06f2.\u06f0", RAISES),  # Extended Arabic-Indic
    ("\u0662", RAISES),
    ("2.\u0660", RAISES),  # ASCII integer part, non-ASCII fraction
    ("2.0\u0660", RAISES),
    ("2e\u0665", RAISES),  # in a decimal exponent
    ("2.0e\uff11", RAISES),
    ("0x\u0661p1", RAISES),  # in a hex mantissa
    ("\u0660x1p3", RAISES),
    # Both accept, and agree.
    ("Infinity", True),
    ("+Infinity", True),
    ("-Infinity", False),
    ("NaN", False),
    (" 1.0 ", False),
    ("\t2.0\n", True),
    ("+2.0", True),
    ("2.", True),
    ("2", True),
    ("1e0", False),
    (".5", False),
    ("-0.0", False),
    # Float32 rounding, where the double answer differs from Java's.
    ("1.99999999", True),
    ("1.9999999404", True),
    ("1.9999999", False),
    ("2.0000001", True),
    ("3.4e39", True),
    # Overflow and underflow, which Java answers with a signed infinity or a
    # signed zero and never by throwing. The hex rows are the ones Python
    # cannot simply be handed: `float.fromhex` raises `OverflowError` past the
    # double range where `float("1e400")` quietly returns infinity, so a port
    # that forwards `float.fromhex` aborts the run on a string the jar reports.
    ("0x1p1024", True),  # past the double range, Java prints Infinity
    ("-0x1p1024", False),
    ("0x1p2000", True),
    ("0x1p128", True),  # inside double, past float: narrowing makes it infinite
    ("-0x1p128", False),
    ("0x1p-1074", False),  # the smallest double, which is zero as a float
    ("0x1p-2000", False),
    ("0xfffffffffffffffffffffp1", True),  # 84 mantissa bits, Java 3.8685626E25
    ("1e400", True),
    ("-1e400", False),
    ("-3.4e39", False),
    ("1e-400", False),
)


def header(version: str) -> Msg:
    """A `FeedHeader` carrying exactly this version string.

    Through the real encoder and decoder, so the value a rule reads is the value
    a feed would carry, including the empty string, which is on the wire as a
    zero-length field and is therefore present.
    """
    return decode(
        encode({"gtfs_realtime_version": version}, V2015, "FeedHeader"), V2015, "FeedHeader"
    )


def header_without_version() -> Msg:
    """A `FeedHeader` with no version at all, built rather than decoded.

    `gtfs_realtime_version` is `required`, so protobuf-java refuses to parse a
    header without it and so does `proto/decode.py`. The absent-version branch
    of `isValidVersion` is therefore unreachable from a real feed; it is still
    the first thing that function tests, so it is still ported and still tested.
    """
    return Msg(V2015.message("FeedHeader"), V2015)


@pytest.mark.parametrize(("version", "expected"), PARSE_ORACLE)
def test_is_v2_or_higher_matches_java(version: str, expected: object) -> None:
    if expected is RAISES:
        with pytest.raises(ValueError):
            is_v2_or_higher(header(version))
    else:
        assert is_v2_or_higher(header(version)) is expected


def test_is_v2_or_higher_raises_on_an_absent_version() -> None:
    """The whole reason the helper raises instead of answering False.

    `HeaderValidator:55-62` swallows this and skips E049; `TimestampValidator`
    `:87-100` has already set its flag to true and therefore logs E048. A helper
    that returned False would make the second half unreachable.
    """
    with pytest.raises(ValueError):
        is_v2_or_higher(header_without_version())


def test_is_valid_version() -> None:
    assert is_valid_version(header("1.0"))
    assert is_valid_version(header("2.0"))
    assert is_valid_version(header_without_version())
    assert not is_valid_version(header("3.0"))
    assert not is_valid_version(header(""))
    assert not is_valid_version(header("2.0f"))
    assert not is_valid_version(header("1.00"))
    assert not is_valid_version(header(" 2.0"))


def test_a_version_java_parses_can_still_be_an_invalid_version() -> None:
    """The two helpers answer different questions and are not each other's negation.

    `"3.0"` is v2 or higher and is not a valid version, which is how a feed can
    be checked for `incrementality` (E049) and reported for its version (E038)
    on the same pass.
    """
    assert is_v2_or_higher(header("3.0"))
    assert not is_valid_version(header("3.0"))
