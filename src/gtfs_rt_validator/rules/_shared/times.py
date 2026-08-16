"""`util/TimestampUtils.java`: the POSIX window, ages, and clock rendering.

Reaches seven of the eleven `TimestampValidator` rules plus E019, E020, E021
and E023. Two of the five functions here produce occurrence text, so they are
output bytes rather than predicates, and both of them differ from the obvious
Python in ways that show up in the diff rather than in a crash:

1. **`seconds_after_midnight_to_clock` is signed arithmetic.** Java truncates
   toward zero and keeps the dividend's sign in `%`; Python floors and takes the
   divisor's sign. E023 feeds it -999 and the two languages disagree. See the
   function.
2. **`posix_to_clock` is the only consumer of the agency timezone in this
   codebase.** Nothing else reads `StaticContext.timezone`, so this is the sole
   path by which a zone reaches a report. It is also called before the caller
   checks `is_posix` (`TimestampValidator.java:187`), so it takes any int64 and
   must not raise.

The two string-format gates E020 and E021 use live in `timeformats.py`; the
split is the file-size hook's, not a conceptual seam. Resolving the zone id
itself lives in `zones.py`, and that one is a seam: `getTimeZone` accepts custom
`GMT+hh:mm` ids that `zoneinfo` knows nothing about, and getting that wrong
moves every clock below by hours.

Everything here was checked against a JDK 17.0.19 run of the same methods,
compiled verbatim from upstream's source. The one measured divergence that
remains is recorded on `posix_to_clock`.
"""

from __future__ import annotations

import datetime as dt

from gtfs_rt_validator.rules._shared.zones import java_time_zone

__all__ = [
    "MAX_POSIX_TIME",
    "MIN_POSIX_TIME",
    "age_millis",
    "is_in_future",
    "is_posix",
    "posix_to_clock",
    "seconds_after_midnight_to_clock",
]

#: `TimestampUtils.java:37-38`, with upstream's own comments. Both bounds are
#: inclusive: `isPosix` is `>=` and `<=`.
MIN_POSIX_TIME = 1104537600  # Jan 1, 2005
MAX_POSIX_TIME = 1991620134  # Feb 10, 2033

_MILLIS_PER_SECOND = 1000
_MILLIS_PER_DAY = 86_400_000

# Java's `long`. `TimeUnit.SECONDS.toMillis` saturates at these rather than
# wrapping, which is why `posix_to_clock` clamps instead of multiplying.
_LONG_MIN = -(2**63)
_LONG_MAX = 2**63 - 1


def is_posix(timestamp: int) -> bool:
    """`TimestampUtils.isPosix` L54-56."""
    return MIN_POSIX_TIME <= timestamp <= MAX_POSIX_TIME


def age_millis(current_time_millis: int, timestamp_sec: int) -> int:
    """`TimestampUtils.getAge` L65-68: how far behind `current_time_millis` it is.

    Negative for a timestamp in the future, which is what `is_in_future` reads.

    No saturation here, unlike `posix_to_clock`. Every caller in
    `TimestampValidator` computes an age only inside the `else` of an
    `if (!isPosix(...))`, so the argument is already inside a 28-year window and
    the `long` overflow Java would suffer on a wilder one is unreachable.
    """
    return current_time_millis - timestamp_sec * _MILLIS_PER_SECOND


def is_in_future(current_time_millis: int, timestamp_sec: int, tolerance_sec: int) -> bool:
    """`TimestampUtils.isInFuture` L200-203, tolerance exclusive.

    Strictly greater, so a timestamp exactly `tolerance_sec` seconds ahead is
    fine and one second more is not. `TimestampValidatorTest.testE050` pins both
    halves at a tolerance of 60.

    `TimeUnit.MILLISECONDS.toSeconds` truncates, so a sub-second remainder is
    discarded before the comparison: 60500 ms in the future is 60 seconds here.
    """
    age = age_millis(current_time_millis, timestamp_sec)
    return age < 0 and abs(age) // _MILLIS_PER_SECOND > tolerance_sec


def _java_divmod(value: int, divisor: int) -> tuple[int, int]:
    """Java's `/` and `%` on two ints: truncate toward zero, sign of the dividend.

    Python's `//` floors and its `%` takes the divisor's sign, so the two agree
    only when `value` is non-negative. Every caller below is `%02d`-formatted
    straight into occurrence text, so the disagreement is a byte difference
    rather than an arithmetic curiosity.
    """
    quotient = abs(value) // divisor
    if value < 0:
        quotient = -quotient
    return quotient, value - quotient * divisor


def seconds_after_midnight_to_clock(seconds_after_midnight: int) -> str:
    """`TimestampUtils.secondsAfterMidnightToClock` L76-78, negatives included.

        String.format("%02d:%02d:%02d", s / 3600, (s / 60) % 60, s % 60)

    The hours are not reduced modulo 24, so a next-service-day time renders as
    "24:00:00" or "29:00:00" and `%02d` widens rather than truncating.

    **The negative case reaches output bytes.** E023 passes
    `StopTime.getArrivalTime()` in unchanged, and onebusaway-gtfs returns its
    `MISSING_VALUE` sentinel of -999 for a stop_time with no arrival_time
    (`StopTime.java:30, 42, 191-195`). Java renders that "00:-16:-39"; the
    floor-and-divisor-sign Python would otherwise produce is "-1:44:21". Hence
    `_java_divmod`. Measured on JDK 17.0.19, not read off the language spec.

    `%02d` on a negative pads to a total width of two *including* the sign, so
    -1 prints as "-1" rather than "-01" or "01". Python's `%02d` agrees.
    """
    hours, _ = _java_divmod(seconds_after_midnight, 3600)
    whole_minutes, _ = _java_divmod(seconds_after_midnight, 60)
    _, minutes = _java_divmod(whole_minutes, 60)
    _, seconds = _java_divmod(seconds_after_midnight, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# `datetime` covers years 1 to 9999 and Java's calendar does not stop there, so
# the offset lookup is clamped to instants `datetime` can build. Two days inside
# each end, so that adding a zone offset cannot walk off either edge.
_OFFSET_FLOOR_MILLIS = int(dt.datetime(1, 1, 3, tzinfo=dt.UTC).timestamp()) * _MILLIS_PER_SECOND
_OFFSET_CEIL_MILLIS = int(dt.datetime(9999, 12, 29, tzinfo=dt.UTC).timestamp()) * _MILLIS_PER_SECOND


def _saturating_millis(posix_time: int) -> int:
    """`TimeUnit.SECONDS.toMillis`, which clamps to the `long` ends rather than wrapping.

    Measured: 9223372036854776 seconds and 2**63-1 seconds both come back as
    2**63-1 milliseconds, and both render the same clock.
    """
    seconds = min(max(posix_time, _LONG_MIN), _LONG_MAX)
    return min(max(seconds * _MILLIS_PER_SECOND, _LONG_MIN), _LONG_MAX)


def posix_to_clock(posix_time: int, timezone: str | None) -> str:
    """`TimestampUtils.posixToClock` L87-93: `SimpleDateFormat("HH:mm:ss")` in a zone.

    Format only, never a comparison. Pinned by `UtilTest.java:281-288`: POSIX
    1493383886 in America/New_York is "08:51:26". DST is honoured at the
    instant in question, which a differential over the 2017 US transition
    checks a second either side of.

    Takes any int64. `TimestampValidator.java:187` renders an arrival time
    before asking whether it is POSIX, and `StopTimeEvent.time` is an int64, so
    a feed carrying 2**63-1 must format rather than fail.

    **Two measured divergences remain**, both outside anything a transit feed
    carries, and both set out below.

    1. `java.util.TimeZone` is the legacy API, and `ZoneInfo.getOffsets`
       answers with the zone's raw offset for any instant before its first
       tzdata transition, discarding the local mean time the file records
       there. `zoneinfo` keeps LMT. So 1874 in America/New_York is "13:40:00"
       from the jar at a flat -05:00 and "13:43:58" here at -04:56:02. Of 315
       (zone, instant) pairs put through both, 292 agree; the 23 that do not
       are all at instants before a first transition, and every instant from
       1900-01-01 on agrees in all fifteen zones.
    2. `datetime` stops at years 1 and 9999, so the offset lookup below is
       clamped to the nearest instant it can build. Java keeps going, and what
       it does out there is not one rule: year 33658 gets the zone's DST rule
       and lands an hour off this, while 2**63-1 seconds lands on standard time
       and agrees. Reducing by whole 400-year Gregorian cycles instead, the
       trick `runner/clock.py` uses for year 0, trades one of those for the
       other.
    """
    millis = _saturating_millis(posix_time)
    lookup = min(max(millis, _OFFSET_FLOOR_MILLIS), _OFFSET_CEIL_MILLIS)
    moment = dt.datetime.fromtimestamp(lookup // _MILLIS_PER_SECOND, tz=dt.UTC)
    offset = moment.astimezone(java_time_zone(timezone)).utcoffset()
    assert offset is not None  # noqa: S101 - an aware datetime always has one
    # `Calendar` derives its fields from a floored division of the local
    # milliseconds, which is what Python's `%` does on a negative dividend, so
    # the second before the epoch is 23:59:59 rather than -00:00:01.
    time_of_day = (millis + int(offset.total_seconds()) * _MILLIS_PER_SECOND) % _MILLIS_PER_DAY
    hours, remainder = divmod(time_of_day // _MILLIS_PER_SECOND, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
