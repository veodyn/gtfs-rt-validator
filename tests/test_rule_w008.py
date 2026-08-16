"""W008, a header timestamp more than 65 seconds older than the current time.

`testW008` (`TimestampValidatorTest.java:216-266`) is upstream's, and it is the
one test in this cohort that cannot be ported literally: it calls
`System.currentTimeMillis()`, so its two stages are "now" and "now minus 70
seconds". This project's clock is a value rather than an observation
(`runner/clock.py`), so the two stages are ported at a fixed instant instead. It
has to be an instant well inside the POSIX window rather than upstream's
`MIN_POSIX_TIME`, because `now - 70` at the floor of the window would be
rejected by `isPosix` and reported as E001 before W008 was ever asked.

Upstream asserts counts only; the prefix and the boundary below are ours.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.upstream.w008 import RULE_ID, check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from rulefixtures import context, entity, message, occurrences, prefixes

#: 2014-05-13, comfortably inside `isPosix`'s 2005 to 2033 window at both ends.
NOW_SECONDS = 1_400_000_000
NOW = Reading(NOW_SECONDS * 1000, ClockSource.FIXED)


def found(tmp_path: Path, header_timestamp: int) -> list[str]:
    feed = message(
        entity(
            trip_update={"trip": {"trip_id": "1.1"}, "timestamp": header_timestamp},
            vehicle={"timestamp": header_timestamp},
        ),
        timestamp=header_timestamp,
    )
    return prefixes(check(feed, context(tmp_path, clock=NOW)))


#: `testW008` in order: the header timestamp relative to the current time, and
#: the count upstream asserts.
UPSTREAM_CASES = ((0, 0), (-70, 1))


@pytest.mark.parametrize(("offset", "expected"), UPSTREAM_CASES)
def test_upstream_cases(tmp_path: Path, offset: int, expected: int) -> None:
    assert len(found(tmp_path, NOW_SECONDS + offset)) == expected


def test_the_prefix_renders_the_age_as_minutes_and_seconds(tmp_path: Path) -> None:
    """`:111`. `ageSeconds` is the whole age in seconds and the prefix prints it
    modulo 60, so 70 seconds reads "1 min 10 sec" rather than "1 min 70 sec"."""
    assert found(tmp_path, NOW_SECONDS - 70) == ["header.timestamp is 1 min 10 sec"]


def test_an_age_of_exactly_sixty_five_seconds_passes(tmp_path: Path) -> None:
    """`ageMillis > TimeUnit.SECONDS.toMillis(65)` is strict, and it is compared
    in milliseconds (`:109`), so the boundary is 65000 rather than 65."""
    assert found(tmp_path, NOW_SECONDS - 65) == []
    assert found(tmp_path, NOW_SECONDS - 66) == ["header.timestamp is 1 min 6 sec"]


def test_an_age_under_a_minute_still_prints_the_minutes(tmp_path: Path) -> None:
    """`TimeUnit` truncates, so a 70 second age is 1 minute and a 66 second age
    is also 1 minute; there is no shorter form of the sentence."""
    assert found(tmp_path, NOW_SECONDS - 130) == ["header.timestamp is 2 min 10 sec"]


def test_a_future_header_timestamp_is_not_stale(tmp_path: Path) -> None:
    """The age is negative there, and E050 is the rule that reports it."""
    assert found(tmp_path, NOW_SECONDS + 3600) == []


def test_a_non_posix_header_timestamp_is_e001_and_never_reaches_this(tmp_path: Path) -> None:
    """`:102-118`: W008 lives in the `else` of the POSIX test, so a header in
    milliseconds is reported once as E001 and not also as an enormous age."""
    assert found(tmp_path, NOW_SECONDS * 1000) == []


def test_an_absent_header_timestamp_is_w001_or_e048_and_never_reaches_this(
    tmp_path: Path,
) -> None:
    feed = message(entity(trip_update={"trip": {}}))

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == []


def test_the_occurrence_locates_the_header(tmp_path: Path) -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone."""
    feed = message(entity(), timestamp=NOW_SECONDS - 70)
    (one,) = occurrences(check(feed, context(tmp_path, clock=NOW)))

    assert (one.rule_id, one.context[ENTITY_PATH_KEY]) == (RULE_ID, "header")


def test_the_agency_timezone_does_not_reach_this_prefix(tmp_path: Path) -> None:
    """W008 is the one rule in the block whose text is an age rather than a
    clock, so it is the same bytes in every zone. E050 next to it is not."""
    feed = message(entity(), timestamp=NOW_SECONDS - 70)
    in_tokyo = context(tmp_path, clock=NOW, timezone="Asia/Tokyo")

    assert prefixes(check(feed, in_tokyo)) == ["header.timestamp is 1 min 10 sec"]
