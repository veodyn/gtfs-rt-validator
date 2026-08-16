"""How Java turns a value into the bytes of an occurrence prefix.

Every function here is a place where the obvious Python renders different bytes
than the Java upstream runs, so each one is pinned by `tests/test_shared_javafmt.py`
and re-derived from a running JVM by `tools/diff_javafmt_against_java.py` through
`tools/DumpJavaFormat.java`. Reaches E026, E027, E028, E029 and W004 through
`float32_str`, and W004, E028 and E029 through `fmt2`.

**These are JDK 17's renderings, not "the shortest decimal".** `Float.toString`
was rewritten in JDK 19 to emit the shortest string that round-trips; before
that it sometimes emits one digit more, which is why `_floatingdecimal.py` ports
the old algorithm instead of this module calling `repr`. That module's docstring
has the measurement. Upstream targets 17 and `tools/jarenv.py` refuses to run a
differential under any other JDK, so the compat bytes depend on the JVM as well
as on the jar.

`fmt2` is `String.format("%.2f", ...)`, which is HALF_UP over those same digits
rather than over the exact binary value: the double nearest 2.675 is
2.67499999999999982, and Java still prints "2.68". Java's `Formatter` widens a
`float` argument to `double` before choosing digits, so a rule holding a
protobuf float hands `fmt2` the widened value, which in Python it already is.

Nothing here reads a locale. Upstream calls `String.format` with none, so its
separator is the default locale's; the jar's own environment writes a dot, which
`tools/diff_javafmt_against_java.py` re-checks on every run rather than assuming.

Unit conversion is not here. `toMilesPerHour` and `toMiles` are
`util/GtfsUtils.java` rather than formatting, and they live in
`_shared/positions.py`; `float32` is exported so that module can do the `float`
arithmetic Java does without a second copy of the narrowing.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Context, Decimal

from gtfs_rt_validator.rules._shared import _floatingdecimal

__all__ = [
    "double_str",
    "float32",
    "float32_str",
    "fmt2",
    "int32",
    "int32_str",
    "int64",
    "int64_str",
    "java_bool",
    "java_enum",
    "java_list",
    "java_str",
]


def int32(value: int) -> int:
    """A protobuf `uint32` as protobuf-java's getter hands it back: **signed**.

    Java has no unsigned integer type, so protobuf-java 2.6.1 maps `uint32` to
    `int` and `uint64` to `long`. A value past the signed maximum comes back
    negative. Measured on JDK 17:

        4294967295 -> -1
        4294967294 -> -2
        2147483648 -> -2147483648
        2147483647 ->  2147483647

    **This is what a rule sees, for every purpose.** Not only the rendering: a
    rule that sorts stop_sequences, or compares one against a GTFS row, is
    comparing the `int` this returns, and upstream sorting 4294967295 below 1 is
    the behaviour rather than a bug to avoid reproducing. `StopTimeUpdateValidator`
    fills `List<Integer> rtStopSequenceList` from `getStopSequence()` (`:111`,
    `:114`) and then asks `Ordering.natural().isStrictlyOrdered` of it (`:184`);
    a feed sending 1 then 4294967295 is `[1, -1]` there, and the jar emits E002.

    The decoder stays unsigned, because that is what the wire says and what
    modern mode wants. The narrowing belongs here, at the rule layer's boundary,
    which is why this sits beside `float32`: both are Java's own conversion of a
    decoded value, applied where Java applies it.

    The `uint32` fields a rule reads are `TripUpdate.StopTimeUpdate.stop_sequence`,
    `TripDescriptor.direction_id` and `VehiclePosition.current_stop_sequence`;
    the last of those is read by nothing, here or upstream.

    Idempotent, so a value narrowed twice is unchanged and a caller does not have
    to track which side of the boundary it is on.
    """
    number = int(value) & 0xFFFFFFFF
    return number - (1 << 32) if number & 0x80000000 else number


def int64(value: int) -> int:
    """A protobuf `uint64` as protobuf-java's getter hands it back. See `int32`.

    Measured on JDK 17: `18446744073709551615` comes back as `-1` and
    `9223372036854775808` as `-9223372036854775808`.

    Also the wrap for `long` **arithmetic** on those values, which is why
    `_shared/walk_timestamp` narrows a difference of two header timestamps
    rather than only the two operands: Java's `-` wraps at 64 bits and Python's
    does not.

    The `uint64` fields a rule reads are the three `timestamp` fields and
    `TimeRange.start` / `TimeRange.end`.
    """
    number = int(value) & 0xFFFFFFFFFFFFFFFF
    return number - (1 << 64) if number & (1 << 63) else number


def int32_str(value: int) -> str:
    """A protobuf `uint32` as Java prints it, for a site that only renders.

    `str(int32(v))`. Named apart because a site that reads a field and
    interpolates it without comparing it says so by calling this, and because
    `java_str` refuses to guess a width.
    """
    return str(int32(value))


def int64_str(value: int) -> str:
    """A protobuf `uint64` as Java prints it, for a site that only renders.

    No caller in `src/` today, and that is a fact about the rules rather than
    about this function: every `uint64` a rule reads is also compared, against
    zero, against the POSIX window or against another timestamp, so those sites
    take `int64` and interpolate the narrowed value. This is the spelling for a
    site that does not, and it is the pair of `int32_str`.
    """
    return str(int64(value))


#: Enough room for the widest value `quantize` can be handed, which is a double
#: with 309 integer digits plus the two decimals. The default context's 28
#: would raise `InvalidOperation` instead of rounding.
_WIDE = Context(prec=400, rounding=ROUND_HALF_UP)
_TWO_PLACES = Decimal("0.01")


def float32(value: float) -> float:
    """The float32 nearest `value`, as Java's `(float)` narrowing gives it.

    Round-half-even, and overflow to an infinity rather than the `OverflowError`
    `struct.pack` raises on its own, because `(float) 1e39` is `Infinity` in
    Java and not a failure. A value that came off the wire through
    `proto.decode` is already a float32 and passes through unchanged; this is
    for a value some arithmetic produced.
    """
    if math.isinf(value) or math.isnan(value):
        return value
    try:
        return struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError:
        return math.copysign(math.inf, value)


def float32_str(value: float) -> str:
    """`Float.toString(f)`, as JDK 17 writes it, for a protobuf `float`."""
    bits = struct.unpack("<I", struct.pack("<f", float32(value)))[0]
    negative, digits, dec_exp = _floatingdecimal.float_digits(bits, compatible=True)
    if digits is None:
        return _exceptional(negative, bits & 0x7FFFFF)
    return _java_format(negative, digits, dec_exp)


def double_str(value: float) -> str:
    """`Double.toString(d)`, for the buffer constants and any `double` field.

    `GtfsMetadata.REGION_BUFFER_METERS` is a `double`, so it prints "1609.0",
    never "1609". Python's `repr` agrees on that one but not on 1.0E7, where it
    writes "10000000.0".
    """
    bits = struct.unpack("<Q", struct.pack("<d", value))[0]
    negative, digits, dec_exp = _floatingdecimal.double_digits(bits, compatible=True)
    if digits is None:
        return _exceptional(negative, bits & _floatingdecimal.SIGNIF_MASK)
    return _java_format(negative, digits, dec_exp)


def fmt2(value: float) -> str:
    """`String.format("%.2f", value)`: HALF_UP on the digits, not on the bits.

    `Formatter.print(double)` takes `Math.abs(value)` and emits the sign itself,
    which is why `-0.0` renders "-0.00" and why a value that rounds away to zero
    keeps its sign. `FormattedFloatingDecimal.applyPrecision` then rounds the
    digit array up when the first dropped digit is at least '5', which over the
    decimal those digits denote is exactly `ROUND_HALF_UP`.
    """
    if math.isnan(value):
        return "NaN"
    sign = "-" if math.copysign(1.0, value) < 0 else ""
    if math.isinf(value):
        return f"{sign}Infinity"
    bits = struct.unpack("<Q", struct.pack("<d", abs(value)))[0]
    _negative, digits, dec_exp = _floatingdecimal.double_digits(bits, compatible=False)
    exact = Decimal(f"0.{digits}E{dec_exp}")
    return sign + f"{_WIDE.quantize(exact, _TWO_PLACES):f}"


def java_bool(value: bool) -> str:
    """`"" + booleanValue`, which is lower case where Python's `str` is not."""
    return "true" if value else "false"


def java_str(value: object) -> str:
    """One value concatenated into a Java string.

    A `float` is refused rather than guessed at: the same Python float is a Java
    `float` in a `Position` and a Java `double` in a buffer distance, and the two
    render differently. Call `float32_str` or `double_str` and say which.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return java_bool(value)
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list | tuple):
        return java_list(value)
    raise TypeError(
        f"{type(value).__name__} has no single Java rendering here; a float needs "
        f"float32_str or double_str, which give different bytes for the same value"
    )


def java_list(values: Iterable[object]) -> str:
    """`List<String>.toString()` and `List<Integer>.toString()`.

    Comma and space, no quotes, `null` for an absent element. Python's
    `str(list)` quotes its strings and writes `None`.
    """
    return "[" + ", ".join(java_str(value) for value in values) + "]"


def java_enum(value: int, constants: Mapping[str, int]) -> str:
    """`Enum.toString()` for a protobuf enum, which is the constant name.

    Takes the schema's own `{name: number}` map, so the names come from the
    generated schema module and never from a second copy inside a rule. Where
    two names share a number, the first declared wins, which is what protobuf's
    generated `valueOf` returns.
    """
    for name, number in constants.items():
        if number == value:
            return name
    raise ValueError(
        f"no enum constant has the number {value}; a proto2 enum is closed and the "
        f"decoder leaves an unknown number in the unknown-field bytes instead"
    )


def _exceptional(negative: bool, fract: int) -> str:
    """Java's NaN and infinity images, which carry no sign for NaN."""
    if fract:
        return "NaN"
    return "-Infinity" if negative else "Infinity"


def _java_format(negative: bool, digits: str, dec_exp: int) -> str:
    """`BinaryToASCIIBuffer.getChars`: where the point goes, and when E-form wins.

    The switch is on the decimal exponent rather than on a comparison against
    1e-3 and 1e7, which is what makes a value just under a threshold land on the
    side its own digits put it: `9.999999E-4` is E-form, `0.001` is not.
    """
    sign = "-" if negative else ""
    count = len(digits)
    if 0 < dec_exp < 8:
        head = digits[: min(count, dec_exp)]
        if count < dec_exp:
            return f"{sign}{head}{'0' * (dec_exp - count)}.0"
        return f"{sign}{head}.{digits[dec_exp:] or '0'}"
    if -3 < dec_exp <= 0:
        return f"{sign}0.{'0' * -dec_exp}{digits}"
    mantissa = f"{digits[0]}.{digits[1:] or '0'}"
    exponent = f"-{1 - dec_exp}" if dec_exp <= 0 else str(dec_exp - 1)
    return f"{sign}{mantissa}E{exponent}"
