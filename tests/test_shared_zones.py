"""`TimeZone.getTimeZone`, including the custom GMT-offset ids `zoneinfo` lacks.

`java.util.TimeZone.getTimeZone` resolves an id in two steps: the tz database
first, then its own **custom id** grammar, and only then GMT. The middle step is
what `zoneinfo` has no equivalent for, and it is not a curiosity: a `agency.txt`
carrying "GMT+05:00" is resolved by the jar to a fixed +5 zone and by a naive
port to UTC, which is a five-hour difference in every clock the seven rules that
render one write out.

Every row here was measured on the JDK 17.0.19 that `tools/jarenv.py` selects,
by a single-file source-launcher program calling `TimeZone.getTimeZone(id)` and
formatting through `SimpleDateFormat("HH:mm:ss")`, which is what
`TimestampUtils.posixToClock` does. The grammar in `_shared/zones.py` was then
diffed against that JVM over 7850 generated ids, every string of the form `GMT`
plus a sign plus up to five characters drawn from `0`, `1`, `5`, `9` and `:`,
plus twenty hand-picked boundary cases. 838 of the 7850 resolve to an offset and
7012 fall back to GMT; the port agrees on all 7850.

The instant is upstream's own, `UtilTest.java:281-288`, so a zone that resolves
to UTC renders "12:51:26" and any row that differs from it proves an offset was
applied.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.rules._shared.times import posix_to_clock

#: `UtilTest.java:281-288`, 2017-04-28T12:51:26Z.
INSTANT = 1493383886

#: What a zone resolving to GMT renders at `INSTANT`.
GMT_CLOCK = "12:51:26"

#: Every shape of custom id the JVM accepts, with the clock it produced. The
#: grammar is `GMT`, a sign, then `hh:mm`, `hhmm`, `hmm`, `hh` or `h`; a
#: colonless run of more than two digits splits as `num / 100` and `num % 100`,
#: which is why "GMT+123" is 01:23 and "GMT+00000" is 00:00 rather than a
#: length error.
ACCEPTED: tuple[tuple[str, str], ...] = (
    ("GMT+5", "17:51:26"),  # one-digit hour
    ("GMT+05", "17:51:26"),
    ("GMT+05:00", "17:51:26"),
    ("GMT+9", "21:51:26"),
    ("GMT-5", "07:51:26"),
    ("GMT+0530", "18:21:26"),  # four digits, hhmm
    ("GMT+05:30", "18:21:26"),
    ("GMT+5:30", "18:21:26"),  # one-digit hour with a colon
    ("GMT-3:30", "09:21:26"),
    ("GMT-03:30", "09:21:26"),
    ("GMT-0330", "09:21:26"),
    ("GMT+123", "14:14:26"),  # three digits, hmm
    ("GMT+1234", "01:25:26"),
    ("GMT+059", "13:50:26"),  # leading zero, so hours 0 and minutes 59
    ("GMT+23:59", "12:50:26"),  # the largest offset the grammar allows
    ("GMT+0", GMT_CLOCK),  # a zero offset is still a resolved id
    ("GMT+00", GMT_CLOCK),
    ("GMT+000", GMT_CLOCK),
    ("GMT+00000", GMT_CLOCK),  # five digits, and still 00:00
    ("GMT+000000", GMT_CLOCK),  # six, so there is no length cap at all
    ("GMT-0", GMT_CLOCK),
)

#: Ids the JVM refuses, every one of which falls back to GMT rather than
#: throwing. Grouped by what makes each illegal.
REJECTED: tuple[str, ...] = (
    # Nothing after the sign: the id is shorter than "GMT" plus two.
    "GMT+",
    "GMT-",
    # Hours out of range. The check is `hours > 23`, applied after the split.
    "GMT+24",
    "GMT+24:00",
    "GMT+25",
    "GMT+99:00",
    "GMT+12345",  # five digits split to hours 123
    # Minutes out of range: `num > 59`.
    "GMT+05:99",
    "GMT+0560",
    # A colon demands exactly two digits after it, and at most two before it.
    "GMT+5:5",
    "GMT+05:5",
    "GMT+05:0",
    "GMT+2:0",
    # Not a digit, not a colon, or a second sign.
    "GMT+5.5",
    "GMT+A",
    "GMT++5",
    "GMT+-5",
    "GMT+ 5",
    # The prefix is matched exactly, and neither end is trimmed.
    "gmt+05:00",
    "GMT+05:00 ",
    " GMT+05:00",
    "UTC+05:00",
    "+05:00",
    # Not a custom id at all, and not a zone either.
    "NotAZone",
)

#: Ids the tz database resolves, which are looked up before the grammar is
#: tried and must not be swallowed by it. "GMT0" is a real tzdb link whose name
#: starts with "GMT", and "Etc/GMT+5" carries POSIX' inverted sign, so both
#: would be wrong if the grammar ran first or ran too eagerly.
FROM_THE_TZ_DATABASE: tuple[tuple[str, str], ...] = (
    ("GMT", GMT_CLOCK),
    ("GMT0", GMT_CLOCK),
    ("Etc/GMT+5", "07:51:26"),
    ("America/New_York", "08:51:26"),
)


@pytest.mark.parametrize(("timezone", "expected"), ACCEPTED)
def test_a_custom_gmt_offset_id_resolves_to_its_offset(timezone: str, expected: str) -> None:
    assert posix_to_clock(INSTANT, timezone) == expected


@pytest.mark.parametrize("timezone", REJECTED)
def test_an_id_the_grammar_refuses_falls_back_to_gmt(timezone: str) -> None:
    """Silently, exactly as an id like "NotAZone" does. `getTimeZone` never
    throws for a string; it returns a GMT zone, and every rule that renders a
    clock therefore renders one."""
    assert posix_to_clock(INSTANT, timezone) == GMT_CLOCK


@pytest.mark.parametrize(("timezone", "expected"), FROM_THE_TZ_DATABASE)
def test_a_real_zone_still_wins(timezone: str, expected: str) -> None:
    assert posix_to_clock(INSTANT, timezone) == expected


@pytest.mark.parametrize(
    ("timezone", "expected"), [("GMT+5", "05:00:00"), ("GMT-3:30", "20:30:00")]
)
def test_the_offset_applies_at_the_epoch_too(timezone: str, expected: str) -> None:
    """A second instant, so a row cannot pass by arithmetic coincidence.
    Measured at POSIX 0."""
    assert posix_to_clock(0, timezone) == expected


@pytest.mark.parametrize(
    ("timezone", "expected"), [("GMT+5", "04:59:59"), ("GMT+0", "23:59:59"), ("GMT+", "23:59:59")]
)
def test_a_custom_offset_survives_a_negative_posix_time(timezone: str, expected: str) -> None:
    """The second before the epoch, where the floored modulus in `posix_to_clock`
    is what keeps the clock at 23:59:59 rather than -00:00:01. Measured."""
    assert posix_to_clock(-1, timezone) == expected


def test_a_custom_offset_zone_has_no_daylight_saving() -> None:
    """A custom id is a fixed offset, so the 2017 US spring-forward that moves
    America/New_York by an hour moves "GMT-5" by nothing. Measured: both
    instants are one second apart and the clocks are too."""
    assert posix_to_clock(1489301999, "GMT-5") == "01:59:59"
    assert posix_to_clock(1489302000, "GMT-5") == "02:00:00"
