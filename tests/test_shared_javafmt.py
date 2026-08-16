"""One test per Java rendering that reaches compat occurrence bytes.

Every expected string here was **measured**, not computed by hand. They come
from `tools/DumpJavaFormat.java` run under JDK 17.0.19, the release upstream's
pom targets, and `tools/diff_javafmt_against_java.py` re-runs the same
comparison over a corpus far wider than this file. What is pinned here is the
handful of values that explain *why* each helper exists, so a regression names
the Java behaviour it broke rather than just a diff.

The JDK version is part of the contract and not an implementation detail.
`Float.toString` and `Double.toString` were rewritten in JDK 19 (JDK-4511638) to
emit the shortest round-tripping decimal. `javafmt` reproduces the older
`jdk.internal.math.FloatingDecimal`, which is what a jar run on 17 produces and
which is *not* always the shortest string.
"""

from __future__ import annotations

import math
import struct

import pytest

from gtfs_rt_validator.proto import schema_2015
from gtfs_rt_validator.rules._shared.javafmt import (
    double_str,
    float32,
    float32_str,
    fmt2,
    java_bool,
    java_enum,
    java_list,
    java_str,
)


def f32(value: float) -> float:
    """The float32 a protobuf `float` field would have decoded to."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


# ---------------------------------------------------------------------------
# Float.toString
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.0, "1.0"),
        (100.0, "100.0"),
        (13.0, "13.0"),
        (-13.0, "-13.0"),
        (31.0, "31.0"),
        (0.0, "0.0"),
        (9999999.0, "9999999.0"),
        # 1e7 and 1e-3 are the two thresholds. At or above 1e7, and below 1e-3,
        # Java switches to computerised scientific notation.
        (1e7, "1.0E7"),
        (0.001, "0.001"),
        (1e-4, "1.0E-4"),
        # Coordinates and speeds out of upstream's own VehicleValidatorTest.
        # Python's repr of the same float32 is 27.948284149169922, the shortest
        # form that round-trips as a *double*; Java prints the float32 one.
        (27.9482837, "27.948284"),
        (-82.4131679534912, "-82.41317"),
        (28.057438520876673, "28.057438"),
        (-82.43475437164307, "-82.43475"),
        (0.005, "0.005"),
        (2.675, "2.675"),
        (3.4028235e38, "3.4028235E38"),
    ],
)
def test_float32_str_matches_java(value: float, expected: str) -> None:
    assert float32_str(f32(value)) == expected


def test_float32_str_keeps_the_sign_of_negative_zero() -> None:
    """Java prints the sign bit, and `-0.0 == 0.0` in Python, so test the bits."""
    assert float32_str(-0.0) == "-0.0"
    assert float32_str(0.0) == "0.0"


@pytest.mark.parametrize(
    ("bits", "expected"),
    [
        (0x00000001, "1.4E-45"),  # Float.MIN_VALUE, the smallest subnormal
        (0x007FFFFF, "1.1754942E-38"),  # the largest subnormal
        (0x00800000, "1.17549435E-38"),  # Float.MIN_NORMAL
        (0x7F800000, "Infinity"),
        (0xFF800000, "-Infinity"),
        (0x7FC00000, "NaN"),
        (0x7F800001, "NaN"),  # a NaN with a payload is still bare "NaN"
    ],
)
def test_float32_str_on_bit_patterns(bits: int, expected: str) -> None:
    assert float32_str(struct.unpack("<f", struct.pack("<I", bits))[0]) == expected


def test_float32_str_is_not_the_shortest_decimal_on_jdk_17() -> None:
    """The measured fact that rules out "just print the shortest float32 repr".

    `1.1884683E13` round-trips to this same float32, so the shortest form has
    eight significant digits. JDK 17 prints nine, because `dtoa` takes an
    integral-value fast path that drops only whole decimal digits of the exact
    integer 11884683067392 and keeps whatever is left. JDK 19 and later print
    the shortest form, so this string is a statement about the JVM upstream
    targets, not about the value.
    """
    value = f32(1.18846831e13)
    assert float32_str(value) == "1.18846831E13"
    assert f32(1.1884683e13) == value


@pytest.mark.parametrize(
    ("bits", "expected"),
    [
        (0x6A6425E2, "6.8953495E25"),
        (0x6A14D8E6, "4.4986323E25"),
        (0x6A0FB25E, "4.3429676E25"),
        (0xEA34BDD5, "-5.4625775E25"),
        (0xE8FFF17E, "-9.6692655E24"),
    ],
)
def test_float32_str_reproduces_javas_own_arithmetic_overflow(bits: int, expected: str) -> None:
    """Five of the twelve floats where unbounded arithmetic gets a different digit.

    `dtoa` runs in `int`, `long` or `FDBigInteger` depending on how large the
    scaled operands are. These take the `long` branch, where `b + m > tens`
    overflows a signed 64-bit sum, reads as false, and skips the rounding step
    that unbounded arithmetic would take. Python would otherwise end each of
    these one higher in the last digit. `tools/diff_javafmt_against_java.py`
    found them, and dropping the branch emulation makes exactly these fail.
    """
    assert float32_str(struct.unpack("<f", struct.pack("<I", bits))[0]) == expected


def test_float32_rounds_a_double_the_way_a_java_cast_does() -> None:
    assert float32(0.005) == struct.unpack("<f", struct.pack("<f", 0.005))[0]
    assert math.isinf(float32(1e39))  # (float) 1e39 is Infinity, not an error
    assert math.isinf(float32(-1e39)) and float32(-1e39) < 0


# ---------------------------------------------------------------------------
# Double.toString
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # GtfsMetadata's buffer constants, which appendix B warns must not print
        # as bare integers.
        (1609.0, "1609.0"),
        (200.0, "200.0"),
        (0.125, "0.125"),
        (1e7, "1.0E7"),
        (1e-4, "1.0E-4"),
        (-1e-4, "-1.0E-4"),
        (12345.6789, "12345.6789"),
        (1.8014398509481984e16, "1.8014398509481984E16"),
    ],
)
def test_double_str_matches_java(value: float, expected: str) -> None:
    assert double_str(value) == expected


# ---------------------------------------------------------------------------
# The two-decimal format helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # The tie that appendix B names: Python's format() rounds half to even
        # and gives "0.12" here.
        (0.125, "0.13"),
        (-0.125, "-0.13"),
        (0.135, "0.14"),
        # Java rounds the shortest decimal representation, not the exact binary
        # value. The double nearest 2.675 is 2.67499999999999982, so C, Python
        # and every exact-value implementation give "2.67".
        (2.675, "2.68"),
        (0.005, "0.01"),
        (0.0001, "0.00"),
        (-0.0001, "-0.00"),
        (0.0, "0.00"),
        (1.0, "1.00"),
        (1609.0, "1609.00"),
        (12345.6789, "12345.68"),
        # A carry that runs off the end of the digits.
        (99.995, "100.00"),
        (-99.995, "-100.00"),
        (1e16, "10000000000000000.00"),
    ],
)
def test_fmt2_matches_java(value: float, expected: str) -> None:
    assert fmt2(value) == expected


def test_fmt2_keeps_the_sign_of_negative_zero() -> None:
    """`Double.compare(-0.0, 0.0) == -1`, so Formatter emits the leading sign."""
    assert fmt2(-0.0) == "-0.00"
    assert fmt2(0.0) == "0.00"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(math.nan, "NaN"), (math.inf, "Infinity"), (-math.inf, "-Infinity")],
)
def test_fmt2_on_exceptional_values(value: float, expected: str) -> None:
    assert fmt2(value) == expected


def test_fmt2_widens_a_float_before_choosing_digits() -> None:
    """`Formatter.print(float)` delegates to `print((double) value)`.

    So the digits come from the *double* nearest the float32, never from the
    float32's own shortest decimal. 0.005f is 0.004999999888241291 as a double,
    which rounds to "0.00", while the double 0.005 rounds to "0.01". Any rule
    holding a protobuf float must hand `fmt2` the widened value, which in Python
    it already is.
    """
    assert fmt2(f32(0.005)) == "0.00"
    assert fmt2(0.005) == "0.01"
    assert fmt2(f32(2.675)) == "2.67"
    assert fmt2(2.675) == "2.68"


# ---------------------------------------------------------------------------
# Lists, booleans, null and enums
# ---------------------------------------------------------------------------


def test_java_list_has_no_quotes_and_a_space_after_the_comma() -> None:
    assert java_list(["a", "b", "c"]) == "[a, b, c]"
    assert java_list([1, 2, 3]) == "[1, 2, 3]"
    assert java_list([]) == "[]"
    assert java_list(["only"]) == "[only]"


def test_java_list_renders_a_null_element_as_null() -> None:
    assert java_list(["a", None, "c"]) == "[a, null, c]"


def test_java_bool_is_lower_case() -> None:
    assert java_bool(True) == "true"
    assert java_bool(False) == "false"


def test_java_str_renders_none_as_the_literal_null() -> None:
    """A null object concatenated into a Java string is "null", not "None"."""
    assert java_str(None) == "null"
    assert "trip_id " + java_str(None) == "trip_id null"


def test_java_str_refuses_a_float_because_the_width_is_not_knowable() -> None:
    """A Python float is both a Java float and a Java double, and they differ.

    `float32_str` and `double_str` give different strings for the same value, so
    a helper that guessed would put the wrong bytes in an occurrence.
    """
    with pytest.raises(TypeError):
        java_str(1.5)


def test_java_str_renders_a_bool_before_an_int() -> None:
    """`bool` is a subclass of `int` in Python and is not one in Java."""
    assert java_str(True) == "true"
    assert java_list([True, 1]) == "[true, 1]"


def test_java_enum_is_the_protobuf_constant_name() -> None:
    constants = schema_2015.SCHEMA.enums["Alert.Effect"]
    assert java_enum(1, constants) == "NO_SERVICE"
    assert java_enum(8, constants) == "UNKNOWN_EFFECT"
    incrementality = schema_2015.SCHEMA.enums["FeedHeader.Incrementality"]
    assert java_enum(0, incrementality) == "FULL_DATASET"
    assert java_enum(1, incrementality) == "DIFFERENTIAL"


def test_java_enum_refuses_a_number_no_constant_declares() -> None:
    """Unreachable through the decoder, which is exactly why it raises.

    proto2 enums are closed: `proto/decode.py` keeps an unknown number in the
    unknown-field bytes and leaves the field unset, so no rule ever holds one.
    A number arriving here means something else went wrong, and guessing a
    rendering for it would put an invented string in an occurrence.
    """
    with pytest.raises(ValueError, match="4321"):
        java_enum(4321, schema_2015.SCHEMA.enums["Alert.Effect"])
