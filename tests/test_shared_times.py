"""`TimestampUtils`, against upstream's own assertions and against a JDK 17.

Every assertion marked "upstream" is transcribed from the real `UtilTest.java`
and `TimestampValidatorTest.java` in the checkout at `jar-build/upstream/`, not
from a summary of them: `testGetAge` (UtilTest.java:150-157),
`testSecondsAfterMidnightToClock` (250-279), `testPosixToClock` (281-288), and
the 60-versus-61-second tolerance boundary in `testE050`
(TimestampValidatorTest.java:1058-1103).

Everything else is **measured**, not reasoned: a single-file source-launcher
program compiled the seven `TimestampUtils` methods verbatim and printed their
answers on the JDK 17.0.19 that `tools/jarenv.py` selects. That run is what
pins `"00:-16:-39"` below, the saturating behaviour at the ends of int64, and
the `posix_to_clock` table. Nothing here is a hand-computed expectation.

The format-validation half lives in `tests/test_shared_timeformats.py`; the two
split at the file-size hook's warn threshold, not at a conceptual seam.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.rules._shared.times import (
    MAX_POSIX_TIME,
    MIN_POSIX_TIME,
    age_millis,
    is_in_future,
    is_posix,
    seconds_after_midnight_to_clock,
)

# --- POSIX bounds -----------------------------------------------------------


def test_the_two_bounds_are_upstreams_literals() -> None:
    """`TimestampUtils.java:37-38`, with the comments that date them."""
    assert MIN_POSIX_TIME == 1104537600  # Jan 1, 2005
    assert MAX_POSIX_TIME == 1991620134  # Feb 10, 2033


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (MIN_POSIX_TIME, True),
        (MAX_POSIX_TIME, True),
        (MIN_POSIX_TIME - 1, False),
        (MAX_POSIX_TIME + 1, False),
        (0, False),
        (-1, False),
        (1493383886, True),
    ],
)
def test_is_posix_is_inclusive_at_both_ends(timestamp: int, expected: bool) -> None:
    """`>=` and `<=`, so both literals are themselves POSIX."""
    assert is_posix(timestamp) is expected


# --- age --------------------------------------------------------------------


def test_get_age() -> None:
    """Upstream, UtilTest.java:150-157."""
    assert age_millis(1104537600000, 1104527600) == 10000000


def test_age_is_negative_for_a_timestamp_in_the_future() -> None:
    assert age_millis(1_000_000_000_000, 1_000_000_001) == -1000


# --- isInFuture -------------------------------------------------------------

# TimestampValidatorTest.java:1057-1065 builds its clock this way, and its three
# timestamps from it: RECENT is 50 seconds behind, FUTURE_60_SEC is exactly at
# the tolerance and logs nothing, FUTURE_61_SEC is one second past it and logs.
CURRENT_TIME_MILLIS = (MIN_POSIX_TIME + 100) * 1000
NOW_SEC = CURRENT_TIME_MILLIS // 1000
TOLERANCE = 60  # TimestampValidator.IN_FUTURE_TOLERANCE_SECONDS


@pytest.mark.parametrize(
    ("timestamp_sec", "expected"),
    [
        (NOW_SEC - 50, False),  # upstream's RECENT
        (NOW_SEC, False),
        (NOW_SEC + 60, False),  # upstream's FUTURE_60_SEC: at the tolerance, no error
        (NOW_SEC + 61, True),  # upstream's FUTURE_61_SEC: one past it, error
    ],
)
def test_is_in_future_at_the_tolerance_boundary(timestamp_sec: int, expected: bool) -> None:
    """Upstream, TimestampValidatorTest.java:1058-1103.

    Strictly greater than the tolerance, so 60 seconds ahead passes and 61
    fails. The asymmetry is the whole point of the test upstream wrote.
    """
    assert is_in_future(CURRENT_TIME_MILLIS, timestamp_sec, TOLERANCE) is expected


def test_is_in_future_truncates_the_sub_second_remainder() -> None:
    """`TimeUnit.MILLISECONDS.toSeconds` truncates, so 60.5 seconds ahead is 60.

    Measured: with the clock half a second past the second, a timestamp 61
    seconds after that second is 60500 ms in the future, which truncates to 60
    and therefore does not exceed a tolerance of 60.
    """
    assert is_in_future(CURRENT_TIME_MILLIS + 500, NOW_SEC + 61, TOLERANCE) is False


@pytest.mark.parametrize(
    ("current_millis", "timestamp_sec", "expected"),
    [
        (CURRENT_TIME_MILLIS, NOW_SEC + 1, True),
        (CURRENT_TIME_MILLIS + 500, NOW_SEC, False),
    ],
)
def test_is_in_future_with_a_zero_tolerance(
    current_millis: int, timestamp_sec: int, expected: bool
) -> None:
    """A tolerance of 0 still needs a whole second, since the truncation runs first."""
    assert is_in_future(current_millis, timestamp_sec, 0) is expected


# --- secondsAfterMidnightToClock -------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (59, "00:00:59"),
        (1200, "00:20:00"),
        (1250, "00:20:50"),
        (21600, "06:00:00"),
        (21901, "06:05:01"),
        (86399, "23:59:59"),
    ],
)
def test_seconds_after_midnight_to_clock(seconds: int, expected: str) -> None:
    """Upstream, UtilTest.java:250-279, every case it lists."""
    assert seconds_after_midnight_to_clock(seconds) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (86400, "24:00:00"),
        (104400, "29:00:00"),
        (359999, "99:59:59"),
    ],
)
def test_seconds_after_midnight_past_a_day_keeps_counting_hours(
    seconds: int, expected: str
) -> None:
    """No modulo on the hours: a next-service-day time renders as 24 or 29 hours.

    Measured. `%02d` widens rather than truncating, so 99 hours prints in full.
    """
    assert seconds_after_midnight_to_clock(seconds) == expected


def test_seconds_after_midnight_renders_the_missing_arrival_time_as_java_does() -> None:
    """`-999` is `"00:-16:-39"`, and that string reaches output bytes.

    E023 passes `StopTime.getArrivalTime()` straight in, and onebusaway-gtfs
    returns its `MISSING_VALUE` sentinel of -999 for a stop_time with no
    arrival_time (`StopTime.java:30, 42, 191-195`). Java's integer division
    truncates toward zero and its `%` keeps the sign of the dividend, so
    -999/3600 is 0, (-999/60)%60 is -16 and -999%60 is -39. Python's `//`
    floors and its `%` takes the sign of the divisor, so the obvious
    translation gives "-1:44:21" instead and E023's occurrence text differs
    from the jar's for every unset arrival_time in the static feed.

    Measured on JDK 17.0.19 by compiling `String.format("%02d:%02d:%02d",
    -999/3600, (-999/60)%60, -999%60)` and printing it, not reasoned from the
    language spec.
    """
    assert seconds_after_midnight_to_clock(-999) == "00:-16:-39"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00"),
        (-1, "00:00:-1"),
        (-59, "00:00:-59"),
        (-60, "00:-1:00"),
        (-61, "00:-1:-1"),
        (-3600, "-1:00:00"),
        (-3661, "-1:-1:-1"),
    ],
)
def test_seconds_after_midnight_negatives(seconds: int, expected: str) -> None:
    """Java's `%02d` on a negative pads to width 2 counting the sign, so -1 is "-1".

    Not "-01" and not "01". Measured across the whole table above; the -60 and
    -3600 rows are the ones that show a zero field still printing as "00" while
    its neighbour carries the sign.
    """
    assert seconds_after_midnight_to_clock(seconds) == expected
