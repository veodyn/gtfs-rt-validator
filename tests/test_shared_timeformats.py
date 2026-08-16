"""`isValidTimeFormat` and `isValidDateFormat`, the two E020/E021 gates.

Split off `tests/test_shared_times.py` at the file-size hook's warn threshold.
The assertions marked "upstream" are transcribed from the real `UtilTest.java`
in `jar-build/upstream/`: `testDateFormat` (UtilTest.java:159-202) and
`testTimeFormat` (204-248).

The rest are measured on the JDK 17.0.19 that `tools/jarenv.py` selects, by
compiling both methods verbatim, alongside a deliberately lenient formatter, and
printing both answers for every input below. That run is what settles which of
upstream's own "bad dates" fail on the length gate and which fail on field
range, and it is what turned up the resolver-style trap: the formatter is built
with `parseStrict()`, which is parse strictness, and `toFormatter()` leaves the
*resolver* at SMART, so an impossible day of month is clamped rather than
rejected.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.rules._shared.timeformats import (
    is_valid_date_format,
    is_valid_time_format,
)

# --- isValidTimeFormat ------------------------------------------------------


@pytest.mark.parametrize(
    "start_time",
    [
        "00:00:00",
        "02:15:35",
        "22:15:35",
        "25:15:35",  # can exceed 24 hrs, service going into the next service day
        "29:15:35",  # and is capped at 29
        "5:15:35",  # H:MM:SS is ok
    ],
)
def test_valid_times(start_time: str) -> None:
    """Upstream, UtilTest.java:204-228."""
    assert is_valid_time_format(start_time) is True


@pytest.mark.parametrize(
    "start_time",
    [
        "30:15:35",  # anything over 29 hrs fails
        "12345678",
        "abcdefgh",
        "05:5:35",
        "05:05:5",
    ],
)
def test_invalid_times(start_time: str) -> None:
    """Upstream, UtilTest.java:230-247."""
    assert is_valid_time_format(start_time) is False


def test_the_length_gate_is_what_separates_h_mm_ss_from_hh_m_ss() -> None:
    """7 or 8 characters, checked before the pattern, and that is the whole trick.

    `^[0-2]?[0-9]:[0-5][0-9]:[0-5][0-9]$` on its own would also match the
    6-character "5:5:35"-shaped strings the optional first digit allows; the
    gate is what makes "5:15:35" legal and "05:5:35" not. It is the change named
    in the last commit to touch `validation/`, "Allow start_time in H:MM:SS
    format for E020".
    """
    assert is_valid_time_format("5:15:35") is True
    assert is_valid_time_format("1:2:3") is False


@pytest.mark.parametrize(
    ("start_time", "expected"),
    [
        ("0:00:00", True),
        ("09:59:59", True),
        ("29:59:59", True),
        ("9:60:00", False),  # [0-5][0-9] on the minutes
        ("23:59:60", False),  # and on the seconds, so no leap second
        ("005:15:35", False),
        # Arabic-Indic five. The character class is ASCII on both sides, and
        # `DecimalStyle` only ever accepts ASCII digits, so it cannot stand in.
        ("\u0665:15:35", False),
        ("5:15:35\n", False),  # Java's matches() is anchored at both ends
        ("\n5:15:35", False),
    ],
)
def test_time_format_edges(start_time: str, expected: bool) -> None:
    """Measured. The last three are where a naive Python port drifts.

    `Matcher.matches()` requires the whole region, so a trailing newline fails
    in Java; `re.match` with a `$` would have accepted it, since `$` also
    matches before a final newline.
    """
    assert is_valid_time_format(start_time) is expected


# --- isValidDateFormat ------------------------------------------------------


@pytest.mark.parametrize("start_date", ["20170101", "20170427"])
def test_valid_dates(start_date: str) -> None:
    """Upstream, UtilTest.java:159-168."""
    assert is_valid_date_format(start_date) is True


@pytest.mark.parametrize(
    "start_date",
    [
        "2017011",
        "2017/01/01",
        "01/01/2017",
        "01-01-2017",
        "01012017",
        "13012017",
        "20171301",
        "abcdefgh",
        "12345678",
        "2017.01.01",
    ],
)
def test_invalid_dates(start_date: str) -> None:
    """Upstream, UtilTest.java:170-201."""
    assert is_valid_date_format(start_date) is False


@pytest.mark.parametrize("start_date", ["01012017", "12345678"])
def test_two_of_upstreams_bad_dates_fail_on_field_range_not_on_length(start_date: str) -> None:
    """Both are eight characters, so the gate passes them and resolution refuses them.

    "01012017" reads as year 0101, month 20, day 17 and "12345678" as year
    1234, month 56, day 78; `MONTH_OF_YEAR` has range 1..12, so
    `checkValidIntValue` throws and `isValidDateFormat` catches it. A lenient
    formatter would have accepted both, which is what makes this a resolution
    failure rather than a syntax one: measured on the JDK 17 run, where a
    `parseLenient()` formatter with `ResolverStyle.LENIENT` returned true for
    each while the real one returned false.
    """
    assert len(start_date) == 8
    assert is_valid_date_format(start_date) is False


@pytest.mark.parametrize(
    ("start_date", "expected"),
    [
        # SMART resolution clamps the day of month rather than rejecting it, so
        # an impossible calendar date is a *valid* start_date to E021.
        ("20170230", True),  # February 30th
        ("20170229", True),  # 2017 is not a leap year
        ("20170431", True),  # April has 30 days
        # The range checks that do bite, all of them from `checkValidIntValue`.
        ("20170132", False),  # DAY_OF_MONTH range is 1..31
        ("20170100", False),  # and starts at 1
        ("20170001", False),  # MONTH_OF_YEAR range is 1..12
        ("00000101", False),  # YEAR_OF_ERA starts at 1, and `yyyy` is year-of-era
        # Eight characters, but not eight ASCII digits.
        ("20170a01", False),
        ("2017 101", False),
        ("+2017011", False),  # the sign is consumed, leaving too few digits for `dd`
        ("\uff12\uff10\uff11\uff17\uff10\uff11\uff10\uff11", False),  # full-width
        ("\u0662\u0660\u0661\u0667\u0660\u0661\u0660\u0661", False),  # Arabic-Indic
        # Both ends of the four-digit year.
        ("99991231", True),
        ("00010101", True),
    ],
)
def test_date_format_edges(start_date: str, expected: bool) -> None:
    """Measured, every row.

    The clamping rows are the surprise: `new DateTimeFormatterBuilder()
    .parseStrict()...toFormatter()` sets *parse* strictness and leaves
    `getResolverStyle()` at SMART, which is `AbstractChronology.resolveYMD`'s
    "previous valid day" branch. Calling this a strict `yyyyMMdd` parse and
    rejecting February 30th would have been a compat failure on any feed that
    sends one.
    """
    assert is_valid_date_format(start_date) is expected


def test_the_length_gate_is_what_rejects_a_start_date_with_anything_after_it() -> None:
    """The gate still earns its place, but not for the reason the comment gives.

    Upstream's comment reads "SimpleDateFormat doesn't catch 2017011 as bad
    format, so check length first", and that was true of the `SimpleDateFormat`
    this code no longer uses. Measured on the JDK 17 run: the current
    `DateTimeFormatter` refuses "2017011" on its own, because `yyyy` is
    adjacent-value parsed and gives back the four digits `MM` and `dd` need,
    leaving one digit for a two-digit field.

    What the gate does catch is a longer string. `parse(text, ParsePosition)`
    with a non-null position does not require the whole input to be consumed,
    so "20170101XYZ" parses cleanly and only the length check refuses it.
    """
    assert is_valid_date_format("2017011") is False
    assert is_valid_date_format("20170101XYZ") is False
    assert is_valid_date_format("201701011") is False
