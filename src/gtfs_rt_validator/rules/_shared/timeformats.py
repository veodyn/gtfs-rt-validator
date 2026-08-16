"""The two `TimestampUtils` string gates: E020's start_time and E021's start_date.

Split off `times.py` at the file-size hook's warn threshold. Nothing else uses
either function: `isValidTimeFormat` has one caller and so does
`isValidDateFormat`, which is why the traps in them are easy to miss.

Both take a raw field off the wire, so both are handed arbitrary UTF-8. Java
measures length in UTF-16 code units and Python in code points, so a string
holding an astral character is longer to Java than to Python. It cannot change
an answer: every such string fails the pattern or the digit check anyway, and
Java's length is never smaller than Python's, so a string that clears the gate
here clears it there too.
"""

from __future__ import annotations

import re

__all__ = ["is_valid_date_format", "is_valid_time_format"]

# `TimestampUtils.java:44`, verbatim, with `\A`/`\Z` standing in for Java's
# `Matcher.matches()`. Python's `$` also matches before a trailing newline and
# Java's does not, so `^...$` here would accept "5:15:35\n" where the jar
# refuses it.
_TIME_PATTERN = re.compile(r"\A[0-2]?[0-9]:[0-5][0-9]:[0-5][0-9]\Z")

# ASCII digits only, matching `DecimalStyle`, which accepts no other numbering
# system. `str.isdigit` would take Arabic-Indic and full-width digits that the
# jar refuses.
_EIGHT_ASCII_DIGITS = re.compile(r"\A[0-9]{8}\Z")


def is_valid_time_format(start_time: str) -> bool:
    """`TimestampUtils.isValidTimeFormat` L102-109. E020's only helper.

    The length gate runs first and is the whole trick: the pattern's optional
    leading digit would otherwise also match six-character strings like
    "1:2:3". Seven or eight characters is what makes "5:15:35" legal and
    "05:5:35" illegal, and it is the change named in the last commit to touch
    upstream's `validation/`, "Allow start_time in H:MM:SS format for E020".

    Hours run to 29, since service can continue into the next service day;
    "30:15:35" is refused. Minutes and seconds are `[0-5][0-9]`, so there is no
    leap second.
    """
    if len(start_time) not in (7, 8):
        return False
    return _TIME_PATTERN.fullmatch(start_time) is not None


def is_valid_date_format(start_date: str) -> bool:
    """`TimestampUtils.isValidDateFormat` L117-131. E021's only helper.

    Upstream builds the formatter with `parseStrict().parseCaseInsensitive()
    .appendPattern("yyyyMMdd")` and asks whether it parses. Reproduced here as
    a digit check and three range checks, because that is all the Java reduces
    to for an eight-character input:

    - `yyyy` is YEAR_OF_ERA, whose range starts at 1, so "0000" is refused.
    - `MM` is checked against 1..12 and `dd` against 1..31 by
      `AbstractChronology.resolveYMD` before either is used.
    - **The resolver is SMART, not STRICT.** `parseStrict()` sets *parse*
      strictness; `toFormatter()` leaves `getResolverStyle()` at its SMART
      default, which is the "previous valid day" branch. So an impossible
      calendar date is clamped rather than rejected and "20170230" is a valid
      start_date. Measured on JDK 17.0.19; reading the builder as a strict
      parse and rejecting February 30th would have been a compat failure.

    Two of upstream's own bad dates, "01012017" and "12345678", clear the
    length gate and fail on field range: they read as month 20 and month 56. A
    lenient formatter accepts both, which is what identifies the failure as
    resolution rather than syntax.

    The length gate still earns its place, though not for the reason upstream's
    comment gives. `SimpleDateFormat` is long gone from this method, and the
    `DateTimeFormatter` that replaced it refuses "2017011" on its own: `yyyy` is
    adjacent-value parsed and hands back the four digits `MM` and `dd` need,
    leaving one digit for a two-digit field. What the gate catches is a longer
    string, because `parse(text, ParsePosition)` with a non-null position does
    not require the input to be fully consumed and "20170101XYZ" parses.
    """
    if len(start_date) != 8:
        return False
    if _EIGHT_ASCII_DIGITS.fullmatch(start_date) is None:
        return False
    year, month, day = int(start_date[:4]), int(start_date[4:6]), int(start_date[6:])
    return year >= 1 and 1 <= month <= 12 and 1 <= day <= 31
