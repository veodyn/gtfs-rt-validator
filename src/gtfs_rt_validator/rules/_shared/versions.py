"""`header.gtfs_realtime_version`, read exactly as `util/GtfsUtils.java:40-56` reads it.

```java
public static boolean isValidVersion(FeedHeader h) {
    return !h.hasGtfsRealtimeVersion()
        || h.getGtfsRealtimeVersion().equals("1.0")
        || h.getGtfsRealtimeVersion().equals("2.0");
}
public static boolean isV2orHigher(FeedHeader h) {
    return Float.parseFloat(h.getGtfsRealtimeVersion()) >= 2.0f;
}
```

Two functions, and they are not each other's negation: `"3.0"` is v2 or higher
and is not a valid version. E038 asks the first question, E049 and E048 the
second.

Stdlib only, and deliberately no import from `runner/`: a helper that reached
`runner.context` would drag in the static adapter and the sibling package with
it, and this module has no business needing either.
"""

from __future__ import annotations

import re
import struct

from gtfs_rt_validator.proto.decode import Msg

__all__ = ["GTFS_RT_V1", "GTFS_RT_V2", "is_v2_or_higher", "is_valid_version", "parse_java_float"]

#: `GtfsUtils.GTFS_RT_V1` and `GTFS_RT_V2`. Compared as strings, never parsed,
#: which is why `"1.00"` and `" 2.0"` are invalid versions.
GTFS_RT_V1 = "1.0"
GTFS_RT_V2 = "2.0"

_FIELD = "gtfs_realtime_version"

# The grammar in the `Double.valueOf` javadoc, which `Float.parseFloat` shares.
# A decimal needs at least one digit and takes an optional exponent; a hex value
# needs the binary exponent, so `0x1.8` is not a float; both take an optional
# `f`/`F`/`d`/`D` suffix; `NaN` and `Infinity` are case-sensitive and take no
# suffix. Every one of these is measured against JDK 17 in
# `tests/test_shared_versions.py`.
#
# **`[0-9]` and never `\d`.** Python's `\d` matches every Unicode decimal digit,
# Arabic-Indic, Devanagari and fullwidth included, and
# `FloatingDecimal.readJavaFormatString` accepts ASCII `0` to `9` and nothing
# else. Measured on JDK 17: `Float.parseFloat` throws `NumberFormatException`
# for Arabic-Indic, Extended Arabic-Indic, Devanagari and fullwidth digits, in
# the integer part, the fraction and the exponent alike, and a `\d` here
# answered 2.0 for each of them, which would emit E049 where the jar skips it.
# The corpus is `tests/test_shared_versions.py`. The hex class was already
# ASCII, so `0x` and `[0-9a-fA-F]` are left alone.
_ASCII_DIGITS = "[0-9]"
_DECIMAL = (
    rf"(?:{_ASCII_DIGITS}+\.?{_ASCII_DIGITS}*|\.{_ASCII_DIGITS}+)(?:[eE][+-]?{_ASCII_DIGITS}+)?"
)
_HEX = rf"0[xX](?:[0-9a-fA-F]+\.?|[0-9a-fA-F]*\.[0-9a-fA-F]+)[pP][+-]?{_ASCII_DIGITS}+"
_JAVA_FLOAT = re.compile(rf"[+-]?(?:NaN|Infinity|(?:{_DECIMAL}|{_HEX})[fFdD]?)\Z")


def is_valid_version(header: Msg) -> bool:
    """Is the version absent, `"1.0"` or `"2.0"`? E038's whole test."""
    if not header.has(_FIELD):
        return True
    version = header.get(_FIELD)
    return version in (GTFS_RT_V1, GTFS_RT_V2)


def is_v2_or_higher(header: Msg) -> bool:
    """Is the version 2.0 or greater? **Raises `ValueError` on anything else.**

    Upstream reads the field with no `has` guard and hands the result straight
    to `Float.parseFloat`, so an absent or non-numeric version throws
    `NumberFormatException` rather than answering false. That looks like a bug
    and reproducing it is mandatory, because the two call sites catch it and
    disagree about what the failure means:

    * `HeaderValidator.java:55-62` catches it and skips E049 entirely, so a feed
      with a junk version is never asked about `incrementality`.
    * `TimestampValidator.java:87-100` pre-initialises its flag to `true` before
      the call, so catching leaves the flag set and E048 is logged.

    A helper that returned a tidy `False` would make the second half
    unreachable, and compat would silently lose E048 on exactly the feeds that
    provoke it.

    `ValueError` rather than a project exception, for three reasons. It is not a
    finding about a feed, so it is not an occurrence. It is not a bug in this
    repository, so it is not `RuleContractError`, whose meaning is "a module
    here is wrong"; a feed can genuinely carry `gtfs_realtime_version: "abc"`.
    And `ValueError` is what Python's own `float()` raises on the same input, so
    a caller writing `try: ... except ValueError:` around a parse gets what it
    expects. `DecodeError` would be wrong too: the bytes parsed fine, and
    upstream reaches this only after a successful `parseFrom`.
    """
    return parse_java_float(str(header.get(_FIELD))) >= 2.0


def parse_java_float(text: str) -> float:
    """`Float.parseFloat`, including where it disagrees with Python's `float()`.

    Returns the value as a Python float holding what a Java `float` would hold,
    so a comparison against `2.0f` answers the same. Raises `ValueError` where
    Java raises `NumberFormatException`.

    Java accepts and Python does not: a trailing `f`, `F`, `d` or `D` suffix
    (`"2.0f"`), hex floats with a binary exponent (`"0x1p3"`), and leading or
    trailing characters at or below `U+0020`, control characters included.
    Python accepts and Java does not: `"inf"`, `"nan"` and their other casings
    (Java takes only the exact spellings `Infinity` and `NaN`), digit
    underscores (`"1_0"`), and non-ASCII whitespace such as `U+00A0`.

    The float32 narrowing is the third disagreement and the one most likely to
    reach a report: `"1.99999999"` is below 2.0 as a double and exactly 2.0 as a
    float, so Java answers v2 and an unnarrowed port answers v1.

    **Overflow is a value, never an exception.** `ValueError` out of here means
    one thing only, "Java would have thrown `NumberFormatException`", because
    `rules/upstream/e049.py` catches it to skip the rule and E048 will catch it
    to log. A magnitude past the double range is not that: measured on JDK 17,
    `Float.parseFloat` answers `"0x1p1024"` and `"1e400"` with Infinity and
    `"-0x1p1024"` with -Infinity, and E049 fires on the positive ones. Python
    agrees for the decimal spellings, where `float("1e400")` is infinity, and
    disagrees for the hex ones, where `float.fromhex` raises `OverflowError`.
    `_hex_value` converts that back to the signed infinity Java produced, so an
    overflowing hex version reports rather than aborting the run.

    One known limit, stated rather than hidden: the value is parsed to a double
    and then rounded to float, where Java rounds the decimal to float in one
    step. The two differ only for a decimal that lands within half an ulp of a
    float tie *after* the double rounding, which no plausible version string or
    test corpus here reaches. Fixing it needs exact decimal-to-binary rounding,
    which is a lot of machinery for a field that reads `"2.0"`.
    """
    trimmed = _java_trim(text)
    if not _JAVA_FLOAT.match(trimmed):
        # Java's own message, so a traceback reads like the jar's log.
        raise ValueError(f'For input string: "{text}"')
    body = trimmed.rstrip("fFdD")
    value = _hex_value(body) if "x" in body or "X" in body else float(body)
    return _to_float32(value)


def _hex_value(body: str) -> float:
    """`float.fromhex`, overflowing to a signed infinity instead of raising.

    The pattern has already accepted `body`, so the only thing left that can go
    wrong is the magnitude, and Java's answer for that is `Infinity`. The sign
    is read off the text rather than off the value, because there is no value
    to read it off: the exception carries none. Underflow needs nothing, since
    `float.fromhex("0x1p-2000")` already returns 0.0, which is Java's answer
    too.
    """
    try:
        return float.fromhex(body)
    except OverflowError:
        return float("-inf") if body.startswith("-") else float("inf")


def _java_trim(text: str) -> str:
    """`String.trim`, which strips every character at or below `U+0020`.

    Not `str.strip()`: that strips Unicode whitespace, which is a different set
    at both ends. `U+00A0` is stripped by Python and not by Java; `U+0001` is
    stripped by Java and not by Python.
    """
    start, end = 0, len(text)
    while start < end and text[start] <= " ":
        start += 1
    while end > start and text[end - 1] <= " ":
        end -= 1
    return text[start:end]


def _to_float32(value: float) -> float:
    """The double a Java `float` holding this value would widen to.

    A magnitude too large for a float becomes infinity, as `Float.parseFloat`
    does with `"3.4e39"`; `struct.pack` raises there instead of overflowing.
    """
    try:
        return struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError:
        return float("inf") if value > 0 else float("-inf")
