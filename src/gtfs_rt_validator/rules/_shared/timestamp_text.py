"""The occurrence prefixes `TimestampValidator` builds, and the arithmetic in them.

Split out of `walk_timestamp.py` by the file-size hook rather than by a
conceptual seam, but the seam is real enough: everything here is output bytes
and nothing here decides whether a rule fires. Seven of the eleven rules in that
validator interpolate a clock string, which makes this module and
`_shared/times.posix_to_clock` the only path by which the agency timezone
reaches a report.

Two details are load-bearing and both look like arithmetic pedantry until the
diff shows up.

1. **`TimeUnit.MILLISECONDS.toMinutes` truncates toward zero, and Python's `//`
   floors.** They agree on a positive age and disagree on every negative one,
   which is exactly the E050 case: the timestamp is in the future, so the age is
   negative. Java renders an age of -61000 ms as `1 min 1 sec` (toMinutes gives
   -1, `Math.abs` gives 1); floor division would give -2 and render `2 min`.
   `TimestampValidatorTest.java:1117` pins the string that catches it.
2. **`Math.abs(ageSeconds) % 60`, in that order.** Java's `%` keeps the
   dividend's sign, so `abs(x) % 60` and `abs(x % 60)` happen to agree, but the
   Java is written the first way and so is this.

The `is`/`is less than`/`is equal to` wordings are upstream's own and are
concatenated inline in the Java (`:193-253`). They are named constants here only
so that the eight E022 variants cannot drift apart from each other.
"""

from __future__ import annotations

from gtfs_rt_validator.rules._shared.javafmt import int32_str
from gtfs_rt_validator.rules._shared.times import posix_to_clock

__all__ = [
    "EQUAL_TO",
    "LESS_THAN",
    "clock_and_value",
    "departure_before_arrival",
    "in_future",
    "not_increasing",
    "stale_header",
    "stop_description",
    "to_minutes",
    "to_seconds",
]

_MILLIS_PER_SECOND = 1000
_MILLIS_PER_MINUTE = 60_000
_SECONDS_PER_MINUTE = 60

#: The two relations E022 reports, `:193-245`. Written as whole clauses because
#: that is how they appear in the Java, mid-sentence after the closing paren.
LESS_THAN = "is less than"
EQUAL_TO = "is equal to"


def _truncate(value: int, divisor: int) -> int:
    """Java's integer division: toward zero, where Python's `//` floors."""
    quotient = abs(value) // divisor
    return -quotient if value < 0 else quotient


def to_minutes(millis: int) -> int:
    """`TimeUnit.MILLISECONDS.toMinutes`."""
    return _truncate(millis, _MILLIS_PER_MINUTE)


def to_seconds(millis: int) -> int:
    """`TimeUnit.MILLISECONDS.toSeconds`."""
    return _truncate(millis, _MILLIS_PER_SECOND)


def clock_and_value(posix_time: int, timezone: str | None) -> str:
    """`posixToClock(t, tz) + " (" + t + ")"`, the pair E022, E025 and E050 print.

    The parenthesised number is the raw POSIX **seconds**. E050 also prints the
    current time, and there the parenthesised number is **milliseconds**, which
    is why that one is built by `in_future` rather than by this.
    """
    return f"{posix_to_clock(posix_time, timezone)} ({posix_time})"


def stop_description(stop_time_update) -> str:
    """`TimestampValidator.java:179`, and **it opens with a space**.

    ```java
    stopTimeUpdate.hasStopSequence() ? " stop_sequence " + getStopSequence()
                                     : " stop_id " + getStopId()
    ```

    Not `GtfsUtils.getStopTimeUpdateId`, which spells the same two branches
    without the leading space; the two are not interchangeable and every prefix
    below concatenates this one straight onto the trip id. The `else` arm reads
    `getStopId()` unguarded, so an update carrying neither field gives
    `" stop_id "` with a trailing space, which is upstream's text and not a bug
    to tidy here.

    `getStopSequence()` is a Java `int` here as everywhere, so the stop_sequence
    goes through `javafmt.int32_str` and a `uint32` above 2^31-1 prints as a
    negative. `_shared/ids.stop_time_update_id_text` renders the same field the
    same way; the two texts differ in the leading space and in nothing else, and
    a fix applied to one of them and not the other would make two prefixes
    disagree about one stop.

    Typed loosely on purpose: this module is under the rules layer and has no
    need of the decoder's own type to format a string.
    """
    if stop_time_update.has("stop_sequence"):
        return f" stop_sequence {int32_str(stop_time_update.get('stop_sequence'))}"
    return f" stop_id {stop_time_update.get('stop_id')}"


def stale_header(age_millis: int) -> str:
    """W008, `:111`. Only reached with an age above 65 seconds, so non-negative."""
    return (
        f"header.timestamp is {to_minutes(age_millis)} min "
        f"{to_seconds(age_millis) % _SECONDS_PER_MINUTE} sec"
    )


def in_future(
    label: str,
    moment: str,
    age_millis: int,
    current_time_text: str,
    current_time_millis: int,
) -> str:
    """E050's one sentence, from `:116`, `:164` and `:291`.

    The three sites differ only in `label`: `"header.timestamp"`, the trip id
    followed by `" timestamp"`, or `"vehicle_id <id> timestamp"`. The header
    site applies `Math.abs` inline where the other two applied it when they
    computed the age; both orders give the same string, and the abs lives here
    so that one wording cannot drift from the other two.
    """
    minutes = abs(to_minutes(age_millis))
    seconds = abs(to_seconds(age_millis)) % _SECONDS_PER_MINUTE
    return (
        f"{label} {moment} is {minutes} min {seconds} sec greater than "
        f"{current_time_text} ({current_time_millis})"
    )


def not_increasing(
    where: str,
    field: str,
    moment: str,
    relation: str,
    previous_field: str,
    previous_moment: str,
) -> str:
    """One of E022's eight, `:195-245`. `where` is the trip id plus the stop.

    All eight share this shape and vary in three slots: which field this stop
    carried, whether it is less than or equal to the previous value, and which
    field that previous value came from. Upstream writes all eight out in full;
    writing them once is the only way eleven rule modules can share one loop
    without eight near-identical format strings drifting.
    """
    return f"{where} {field} {moment} {relation} previous stop {previous_field} {previous_moment}"


def departure_before_arrival(where: str, departure: str, arrival: str) -> str:
    """E025, `:248-251`. Within one stop_time_update, never across two."""
    return f"{where} departure_time {departure} is less than the same stop arrival_time {arrival}"
