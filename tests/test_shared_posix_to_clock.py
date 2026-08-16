"""`posixToClock`, the only path by which the agency timezone reaches a report.

Split off `tests/test_shared_times.py` at the file-size hook's cap. Nothing
else in this codebase reads `StaticContext.timezone`, so these rows are the
whole of the timezone's contract with the seven rules that render one.

`test_posix_to_clock` is upstream's own, transcribed from
`UtilTest.java:281-288` in the checkout at `jar-build/upstream/`. Every other
row is measured: a single-file source-launcher program compiled
`posixToClock` verbatim and printed 315 (zone, instant) pairs on the JDK
17.0.19 that `tools/jarenv.py` selects, and this file carries the interesting
ones plus both classes of disagreement that run turned up.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.rules._shared.times import (
    MAX_POSIX_TIME,
    MIN_POSIX_TIME,
    posix_to_clock,
)


def test_posix_to_clock() -> None:
    """Upstream, UtilTest.java:281-288."""
    assert posix_to_clock(1493383886, "America/New_York") == "08:51:26"


@pytest.mark.parametrize(
    ("posix_time", "timezone", "expected"),
    [
        # Either side of the 2017 US spring-forward, one second apart.
        (1489301999, "America/New_York", "01:59:59"),
        (1489302000, "America/New_York", "03:00:00"),
        # The same instant read in five zones, two of them off the hour.
        (1493383886, "UTC", "12:51:26"),
        (1493383886, "Asia/Kathmandu", "18:36:26"),
        (1493383886, "Australia/Lord_Howe", "23:21:26"),
        (1493383886, "Pacific/Chatham", "01:36:26"),
        (1493383886, "Europe/London", "13:51:26"),
        # The epoch and the second before it, which is a negative POSIX time.
        (0, "UTC", "00:00:00"),
        (-1, "UTC", "23:59:59"),
        (0, "America/New_York", "19:00:00"),
        (-1, "America/New_York", "18:59:59"),
        # Upstream's own bounds, so the window the validator calls POSIX renders.
        (MIN_POSIX_TIME, "America/New_York", "19:00:00"),
        (MAX_POSIX_TIME, "America/New_York", "22:48:54"),
    ],
)
def test_posix_to_clock_honours_dst_and_the_zone(
    posix_time: int, timezone: str, expected: str
) -> None:
    """Measured: every row came back identical from the JDK 17 run and from here.

    The agency timezone reaches output bytes through this function and no
    other, so a differential over it is the whole of the timezone's contract.
    """
    assert posix_to_clock(posix_time, timezone) == expected


@pytest.mark.parametrize("timezone", ["Not/AZone", "", "America/Nowhere", None])
def test_posix_to_clock_falls_back_to_gmt_for_a_zone_it_does_not_know(
    timezone: str | None,
) -> None:
    """`TimeZone.getTimeZone` answers GMT for an id it cannot resolve, silently.

    Measured for the string cases. `None` cannot arrive here under compat:
    `BatchProcessor.java:145` calls `TimeZone.getTimeZone(null)`, which throws
    a NullPointerException that kills the run before a rule sees a message, and
    `static/_tables.timezone_of` records that. It is GMT here so that a rule
    reached by any other route renders rather than raising.
    """
    assert posix_to_clock(1493383886, timezone) == "12:51:26"


@pytest.mark.parametrize(
    ("posix_time", "expected"),
    [
        (4102444800, "19:00:00"),  # year 2100
        (253402300799, "18:59:59"),  # 9999-12-31T23:59:59Z, the last `datetime` can build
        (9223372036854775807, "02:12:55"),  # 2**63-1 seconds
        (9223372036854775, "02:12:55"),  # the largest second that survives *1000
        (9223372036854776, "02:12:55"),  # the first that saturates, to the same string
    ],
)
def test_posix_to_clock_never_raises_on_a_timestamp_out_of_any_sane_range(
    posix_time: int, expected: str
) -> None:
    """`StopTimeEvent.time` is an int64 and is rendered before it is checked.

    `TimestampValidator.java:187` calls `posixToClock` on the arrival time and
    only then asks `isPosix`, so a feed carrying 2**63-1 formats rather than
    failing. Java saturates in `TimeUnit.SECONDS.toMillis`, which the last two
    rows pin: one second more than the largest value that can be multiplied out
    gives the same clock as 2**63-1 does.

    Every row was measured, including the three beyond year 9999, which land on
    standard time and so survive the clamping the next section describes.
    """
    assert posix_to_clock(posix_time, "America/New_York") == expected


# --- the two known divergences ---------------------------------------------

# 1874 and year 1 in America/New_York, either side of the zone's 1883 first
# transition, and what the jar answered for each. Both measured.
BEFORE_FIRST_TRANSITION = -3000000000
JAR_BEFORE_FIRST_TRANSITION = "13:40:00"
AFTER_FIRST_TRANSITION = -2208988800  # 1900-01-01, where the two agree again
OUT_OF_RANGE = 1000000000000  # year 33658
JAR_OUT_OF_RANGE = "21:46:40"


@pytest.mark.xfail(
    reason="java.util.TimeZone drops LMT and uses the raw offset before a zone's "
    "first transition; zoneinfo keeps LMT. See the docstring.",
    strict=True,
)
def test_known_divergence_before_a_zones_first_transition() -> None:
    """`zoneinfo` keeps local mean time where `java.util.TimeZone` throws it away.

    `ZoneInfo.getOffsets` answers with the zone's raw offset for any instant
    earlier than its first tzdata transition, so 1874 in America/New_York is
    "13:40:00" from the jar at a flat -05:00 and "13:43:58" here at -04:56:02.

    Both were measured on the JDK 17 run. Of its 315 (zone, instant) pairs, 292
    agree; the 23 that do not are all at the same two instants, 1874 and year 1,
    and every instant from 1900-01-01 on agrees in all fifteen zones.

    What it would take to settle: tzdata's transition times, which `zoneinfo`
    does not expose, since the obvious proxies do not hold. At 1874
    Asia/Kolkata already reports MMT and Pacific/Chatham already reports +1215,
    yet the jar uses the raw offset for both, so testing for an "LMT"
    abbreviation would miss them.

    Observable effect: a feed timestamp older than a zone's first transition,
    rendered by one of the seven rules that call this. `MIN_POSIX_TIME` is 2005
    and E001 flags anything outside the window, but E022's arrival times are
    rendered before that check, so it is reachable rather than impossible.
    """
    assert posix_to_clock(BEFORE_FIRST_TRANSITION, "America/New_York") == (
        JAR_BEFORE_FIRST_TRANSITION
    )


@pytest.mark.xfail(
    reason="GregorianCalendar keeps going past year 9999 and datetime does not; "
    "no single clamping rule reproduces it. See the docstring.",
    strict=True,
)
def test_known_divergence_beyond_the_end_of_datetimes_range() -> None:
    """Year 33658, where the jar applies the zone's DST rule and this cannot.

    `datetime` stops at years 1 and 9999, so the offset is looked up at the
    nearest instant it can build, which for a far-future timestamp is a
    December date in standard time. The jar says "21:46:40" at -04:00 and this
    says "20:46:40" at -05:00.

    What it would take to settle: reproducing `GregorianCalendar` at its own
    overflow boundaries. Reducing by whole 400-year Gregorian cycles, the trick
    `runner/clock.py` uses for year 0, fixes this instant and breaks both ends
    of int64 in exchange: the jar renders 2**63-1 seconds and 2**63 milliseconds
    in standard time, which the clamp already matches and the cycle does not.

    Observable effect: a timestamp roughly 30,000 years out. Nothing else here
    is out of range, and the important half of the contract, that no int64
    raises, is pinned by the test above.
    """
    assert posix_to_clock(OUT_OF_RANGE, "America/New_York") == JAR_OUT_OF_RANGE


def test_the_known_divergences_stay_where_they_are() -> None:
    """A ratchet, not an excuse.

    Pins this side of both gaps so neither can quietly widen, and pins the
    1900-01-01 instant one second-count past the first of them, where the two
    implementations agree again.
    """
    assert posix_to_clock(BEFORE_FIRST_TRANSITION, "America/New_York") == "13:43:58"
    assert posix_to_clock(AFTER_FIRST_TRANSITION, "America/New_York") == "19:00:00"
    assert posix_to_clock(OUT_OF_RANGE, "America/New_York") == "20:46:40"
    # The far past and the low end of int64, measured as "17:13:20" and
    # "11:47:04" from the jar, are the same clamping gap seen from the other
    # side. Pinned so a change to the clamp shows up here.
    assert posix_to_clock(-1000000000000, "America/New_York") == "17:17:18"
    assert posix_to_clock(-(2**63), "America/New_York") == "11:51:02"
