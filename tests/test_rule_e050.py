"""E050, a timestamp further into the future than the tolerance allows.

`testE050` (`TimestampValidatorTest.java:1051-1145`) is upstream's, ported stage
by stage from the checkout at `jar-build/upstream/`, and its assertion at `:1117`
is **the only occurrence text upstream asserts byte for byte anywhere in its
whole suite**:

```java
assertEquals("header.timestamp 19:02:41 (1104537761) is 1 min 1 sec greater than 19:01:40 (1104537700000)",
             results.get(0).getOccurrenceList().get(0).getPrefix());
```

That makes it the single best oracle this project has for the path from an
agency timezone to a report byte, and it is ported here unchanged. It also pins
two things nothing else does: `19:02:41` against `1104537761` fixes
`testagency.zip` on US Eastern time, and `1 min 1 sec` against an age of -61000
milliseconds fixes the truncation as Java's rather than Python's, since floor
division would render the same age as `2 min`.

Everything below `UPSTREAM_CASES` other than that assertion is ours.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.times import MIN_POSIX_TIME
from gtfs_rt_validator.rules.upstream.e050 import RULE_ID, check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from rulefixtures import ENTITY_ID, context, entity, message, occurrences, prefixes

#: `testE050`'s current time: 100 seconds after the floor of the POSIX window.
NOW_MILLIS = (MIN_POSIX_TIME + 100) * 1000
NOW = Reading(NOW_MILLIS, ClockSource.FIXED)
NOW_SECONDS = NOW_MILLIS // 1000

#: Upstream's three fixtures, `:1060-1065`.
RECENT = NOW_SECONDS - 50
FUTURE_60_SEC = NOW_SECONDS + 60
FUTURE_61_SEC = NOW_SECONDS + 61


def a_feed(header: int, trip_update: int, vehicle: int) -> Msg:
    """`testE050`'s entity: neither a trip_id nor a VehicleDescriptor is set."""
    return message(
        entity(
            trip_update={"trip": {}, "timestamp": trip_update},
            vehicle={"timestamp": vehicle},
        ),
        timestamp=header,
    )


#: `testE050` in order: header, TripUpdate and VehiclePosition timestamps, then
#: the count upstream asserts.
UPSTREAM_CASES = (
    (RECENT, RECENT, RECENT, 0),
    (FUTURE_60_SEC, FUTURE_60_SEC, FUTURE_60_SEC, 0),
    (FUTURE_61_SEC, FUTURE_60_SEC, FUTURE_60_SEC, 1),
    (FUTURE_61_SEC, FUTURE_61_SEC, FUTURE_60_SEC, 2),
    (FUTURE_61_SEC, FUTURE_61_SEC, FUTURE_61_SEC, 3),
)


@pytest.mark.parametrize(("header", "trip_update", "vehicle", "expected"), UPSTREAM_CASES)
def test_upstream_cases(
    tmp_path: Path, header: int, trip_update: int, vehicle: int, expected: int
) -> None:
    feed = a_feed(header, trip_update, vehicle)

    assert len(occurrences(check(feed, context(tmp_path, clock=NOW)))) == expected


def test_the_prefix_upstream_pins_byte_for_byte(tmp_path: Path) -> None:
    """`TimestampValidatorTest.java:1117`, ported exactly.

    `testagency.zip`'s agency timezone is not committed to this repository, and
    this assertion is what fixes it: POSIX 1104537761 is 2005-01-01 00:02:41
    UTC, and rendering it `19:02:41` puts the fixture agency five hours behind,
    which is US Eastern in January. `rulefixtures.TESTAGENCY_TIMEZONE` records
    that inference and this is the assertion it rests on.
    """
    feed = a_feed(FUTURE_61_SEC, FUTURE_60_SEC, FUTURE_60_SEC)

    upstreams_assertion = (
        "header.timestamp 19:02:41 (1104537761) is 1 min 1 sec greater than "
        "19:01:40 (1104537700000)"
    )

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == [upstreams_assertion]


def test_exactly_sixty_seconds_in_the_future_passes(tmp_path: Path) -> None:
    """`isInFuture` compares `> tolerance` after truncating to whole seconds
    (`TimestampUtils.java:200-203`), so 60 passes and 61 reports. Upstream's
    second and third stages already say this; the pair is here because it is the
    boundary the rule is entirely about."""
    at_sixty = a_feed(FUTURE_60_SEC, RECENT, RECENT)
    at_sixty_one = a_feed(FUTURE_61_SEC, RECENT, RECENT)

    assert prefixes(check(at_sixty, context(tmp_path, clock=NOW))) == []
    assert len(occurrences(check(at_sixty_one, context(tmp_path, clock=NOW)))) == 1


def test_the_three_prefixes_name_the_header_the_trip_and_the_vehicle(tmp_path: Path) -> None:
    """`:116`, `:164` and `:291`. The parenthesised number after each timestamp
    is raw POSIX **seconds** and the one after the current time is raw
    **milliseconds**, which is upstream's own asymmetry."""
    feed = a_feed(FUTURE_61_SEC, FUTURE_61_SEC, FUTURE_61_SEC)
    tail = f"is 1 min 1 sec greater than 19:01:40 ({NOW_MILLIS})"

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == [
        f"header.timestamp 19:02:41 ({FUTURE_61_SEC}) {tail}",
        f"entity ID {ENTITY_ID} timestamp 19:02:41 ({FUTURE_61_SEC}) {tail}",
        f"vehicle_id  timestamp 19:02:41 ({FUTURE_61_SEC}) {tail}",
    ]


def test_one_current_time_is_rendered_for_the_whole_message(tmp_path: Path) -> None:
    """`:81` computes `currentTimeText` once. Three occurrences naming three
    different seconds would be the failure a per-occurrence render risks, and
    this is the assertion that would see it."""
    feed = a_feed(FUTURE_61_SEC, FUTURE_61_SEC, FUTURE_61_SEC)

    found = prefixes(check(feed, context(tmp_path, clock=NOW)))

    assert {one.rsplit(" greater than ", 1)[1] for one in found} == {f"19:01:40 ({NOW_MILLIS})"}


def test_an_age_past_a_minute_wraps_the_seconds(tmp_path: Path) -> None:
    """`Math.abs(ageSeconds) % 60` (`:116`), so 130 seconds ahead reads
    "2 min 10 sec" rather than "2 min 130 sec"."""
    feed = a_feed(NOW_SECONDS + 130, RECENT, RECENT)

    (one,) = prefixes(check(feed, context(tmp_path, clock=NOW)))

    assert one.endswith(f"is 2 min 10 sec greater than 19:01:40 ({NOW_MILLIS})")


def test_a_non_posix_timestamp_is_e001_and_never_reaches_this(tmp_path: Path) -> None:
    """All three sites live in the `else` of the POSIX test (`:154-166`), so a
    timestamp in milliseconds is reported once rather than also as an age of
    thirty-five thousand years."""
    feed = a_feed(NOW_MILLIS, RECENT, RECENT)

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == []


def test_stop_time_update_times_are_not_checked_for_the_future(tmp_path: Path) -> None:
    """There is no E050 site inside the stop_time_update loop; a predicted
    arrival is *meant* to be in the future."""
    feed = message(
        entity(
            trip_update={
                "trip": {},
                "timestamp": RECENT,
                "stop_time_update": [{"stop_id": "S1", "arrival": {"time": NOW_SECONDS + 3600}}],
            }
        ),
        timestamp=RECENT,
    )

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == []


def test_the_occurrences_locate_each_site(tmp_path: Path) -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone."""
    feed = a_feed(FUTURE_61_SEC, FUTURE_61_SEC, FUTURE_61_SEC)
    found = occurrences(check(feed, context(tmp_path, clock=NOW)))

    assert [one.context[ENTITY_PATH_KEY] for one in found] == [
        "header",
        "entity[0].trip_update",
        "entity[0].vehicle",
    ]
    assert {one.rule_id for one in found} == {RULE_ID}
