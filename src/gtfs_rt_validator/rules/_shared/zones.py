"""`java.util.TimeZone.getTimeZone(String)`, which `zoneinfo` alone cannot answer.

Split off `times.py` at the file-size hook's warn threshold, and it is a real
seam rather than a size one: `posix_to_clock` renders an instant, this resolves
an id, and the second is where every disagreement with the jar about the agency
timezone lives.

`getTimeZone` tries three things in order, and the middle one has no `zoneinfo`
equivalent:

1. the tz database, so "America/New_York" and the link "GMT0" resolve there;
2. its own **custom id** grammar, `GMT` then a sign then an offset, so
   "GMT+05:00" is a fixed +5 zone;
3. GMT, silently, for anything left. `getTimeZone` never throws for a string.

Step 2 is the one this module exists for. A feed whose `agency.txt` carries
"GMT+05:00" is read by the jar at +5 and by a port that knows only steps 1 and 3
at UTC, which is a five-hour difference in every clock the seven rules that
render one write out.

The grammar below is `TimeZone.parseCustomTimeZone` transcribed, and it is
transcribed rather than reasoned because the javadoc's `hh:mm`, `hhmm`, `hh`
summary is not what the code does. Measured on JDK 17.0.19 over 7850 generated
ids: "GMT+123" is 01:23, a three-digit run the javadoc does not mention;
"GMT+00000" and even "GMT+000000" resolve to 00:00, because a colonless run is
split as `num / 100` and `num % 100` with no cap on its length; and "GMT+05:0"
is refused, because a colon demands exactly two digits after it. See
`tests/test_shared_zones.py` for the corpus and the measurement.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

__all__ = ["java_time_zone"]

_GMT = "GMT"

#: `TimeZone.GMT_ID_LENGTH + 2`: "GMT", the sign, and at least one character
#: after it. "GMT+" is one short, which is why it falls back rather than
#: resolving to a zero offset.
_MIN_CUSTOM_LENGTH = len(_GMT) + 2

_MAX_HOURS = 23
_MAX_MINUTES = 59
_MINUTES_PER_HOUR = 60


def java_time_zone(timezone: str | None) -> dt.tzinfo:
    """The zone `TimeZone.getTimeZone` would return, as a `tzinfo`.

    `None` cannot arrive here on a compat run. `BatchProcessor.java:145` calls
    `TimeZone.getTimeZone(null)` for a feed with no agency, which throws a
    NullPointerException and kills the run before a rule sees a message;
    `static/_tables.timezone_of` records that and leaves the decision to the
    runner. GMT here means a rule reached by any other route renders rather
    than raising.

    A machine with no tz database at all would take the final fallback for
    every zone and quietly render every clock in UTC. Nothing in the stdlib
    distinguishes that from an unknown id, and Java's own answer for an unknown
    id is GMT, so it is not made an error here.
    """
    if not timezone:
        return dt.UTC
    from_tzdata = _from_the_tz_database(timezone)
    if from_tzdata is not None:
        return from_tzdata
    minutes = custom_offset_minutes(timezone)
    if minutes is None:
        return dt.UTC
    return dt.timezone(dt.timedelta(minutes=minutes))


def _from_the_tz_database(timezone: str) -> dt.tzinfo | None:
    """Step 1, or `None` so the caller can try step 2.

    An id `zoneinfo` does not know is not an error and must not be logged as
    one: it is how "GMT+05:00" and "NotAZone" both arrive, and `getTimeZone`
    answers the first with an offset and the second with GMT. The two are told
    apart by the grammar, not by this lookup.
    """
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def custom_offset_minutes(timezone: str) -> int | None:
    """`TimeZone.parseCustomTimeZone`: minutes east of GMT, or `None` to refuse.

    Transcribed statement for statement, because three of its behaviours are
    not in the javadoc and all three were measured:

    * A colonless digit run of more than two digits is split arithmetically,
      `hours = num / 100` and `minutes = num % 100`, with **no length limit**.
      So "GMT+123" is 01:23 and "GMT+000000" is 00:00, while "GMT+12345" is
      refused for hours 123 rather than for its length.
    * A colon may appear once, may be preceded by at most two digits, and must
      be followed by exactly two. "GMT+5:30" resolves and "GMT+05:0" does not.
    * The range check is the last thing that happens and covers both fields:
      hours above 23 or minutes above 59 refuse the whole id.

    Digits are ASCII by the same comparison Java uses, `c < '0' || c > '9'`, so
    a fullwidth or Arabic-Indic digit is refused here as it is there. This is
    deliberately not `str.isdigit` and deliberately not a `\\d` class.
    """
    if len(timezone) < _MIN_CUSTOM_LENGTH or not timezone.startswith(_GMT):
        return None
    sign = timezone[len(_GMT)]
    if sign not in "+-":
        return None

    hours = 0
    num = 0
    digits = 0
    seen_colon = False
    for char in timezone[len(_GMT) + 1 :]:
        if char == ":":
            if seen_colon or digits > 2:
                return None
            hours, num, digits, seen_colon = num, 0, 0, True
            continue
        if not ("0" <= char <= "9"):
            return None
        num = num * 10 + (ord(char) - ord("0"))
        digits += 1

    if seen_colon:
        if digits != 2:
            return None
    elif digits <= 2:
        hours, num = num, 0
    else:
        hours, num = divmod(num, 100)

    if hours > _MAX_HOURS or num > _MAX_MINUTES:
        return None
    minutes = hours * _MINUTES_PER_HOUR + num
    return -minutes if sign == "-" else minutes
