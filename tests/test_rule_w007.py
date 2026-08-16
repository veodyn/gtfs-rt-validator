"""W007, more than 35 seconds between consecutive header timestamps.

`testW007` (`TimestampValidatorTest.java:142-211`) is upstream's, ported stage by
stage from the checkout at `jar-build/upstream/`. Its three stages fix the
current header at `MIN_POSIX_TIME + 36` and move the previous one; upstream
asserts counts and never a prefix, so everything below `UPSTREAM_CASES` is ours.

The rule is the third arm of an if/else-if chain (`:123-133`), so the two
boundary cases that matter are not only 35-versus-36 but also "equal" and
"less", which are E017's and E018's and never reach the interval test at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.times import MIN_POSIX_TIME
from gtfs_rt_validator.rules.upstream.w007 import RULE_ID, check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from rulefixtures import context, entity, message, occurrences, prefixes

NOW = Reading(MIN_POSIX_TIME * 1000, ClockSource.FIXED)

#: `testW007`'s current iteration: header, TripUpdate and VehiclePosition all at
#: `MIN_POSIX_TIME + 36`.
CURRENT = MIN_POSIX_TIME + 36


def an_iteration(header_timestamp: int) -> Msg:
    """One iteration, in the shape `testW007` builds: every timestamp equal."""
    return message(
        entity(
            trip_update={"trip": {"trip_id": "1.1"}, "timestamp": header_timestamp},
            vehicle={"timestamp": header_timestamp},
        ),
        timestamp=header_timestamp,
    )


def found(tmp_path: Path, previous: int | None) -> list[str]:
    ctx = context(
        tmp_path, clock=NOW, previous=None if previous is None else an_iteration(previous)
    )
    return prefixes(check(an_iteration(CURRENT), ctx))


#: `testW007` in order: the previous iteration's header timestamp, or `None` for
#: no previous iteration at all, and the count upstream asserts.
UPSTREAM_CASES = (
    (None, 0),
    (MIN_POSIX_TIME + 10, 0),
    (MIN_POSIX_TIME, 1),
)


@pytest.mark.parametrize(("previous", "expected"), UPSTREAM_CASES)
def test_upstream_cases(tmp_path: Path, previous: int | None, expected: int) -> None:
    assert len(found(tmp_path, previous)) == expected


def test_the_prefix_names_the_interval(tmp_path: Path) -> None:
    """`:132`, the interval in seconds and upstream's wording around it."""
    assert found(tmp_path, MIN_POSIX_TIME) == [
        "36 second interval between consecutive header.timestamps"
    ]


def test_an_interval_of_exactly_thirty_five_passes(tmp_path: Path) -> None:
    """`interval > MINIMUM_REFRESH_INTERVAL_SECONDS` is strict (`:130`)."""
    assert found(tmp_path, CURRENT - 35) == []
    assert found(tmp_path, CURRENT - 36) == [
        "36 second interval between consecutive header.timestamps"
    ]


def test_a_previous_header_timestamp_of_zero_is_no_previous_at_all(tmp_path: Path) -> None:
    """`:120` tests the previous *timestamp* as well as the previous message, so
    an unstamped earlier iteration cannot produce an interval of 1104537636."""
    assert found(tmp_path, 0) == []


def test_a_decrease_is_e018_and_never_reaches_the_interval_test(tmp_path: Path) -> None:
    """The chain is if/else-if, so W007 and E018 cannot both fire. Without that,
    an interval of -100 would compare false and this would still pass, so the
    case that proves it is a *positive* interval reached the other way: there is
    none, which is why this asserts the arm rather than the arithmetic."""
    assert found(tmp_path, CURRENT + 100) == []


def test_the_occurrence_locates_the_header(tmp_path: Path) -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone."""
    ctx = context(tmp_path, clock=NOW, previous=an_iteration(MIN_POSIX_TIME))
    (one,) = occurrences(check(an_iteration(CURRENT), ctx))

    assert (one.rule_id, one.context[ENTITY_PATH_KEY]) == (RULE_ID, "header")


def test_a_non_posix_pair_is_still_measured(tmp_path: Path) -> None:
    """`:120-133` is outside the `isPosix` branch, so two timestamps in
    milliseconds still produce an interval and still report here."""
    milliseconds = MIN_POSIX_TIME * 1000
    ctx = context(tmp_path, clock=NOW, previous=an_iteration(milliseconds))

    assert prefixes(check(an_iteration(milliseconds + 36), ctx)) == [
        "36 second interval between consecutive header.timestamps"
    ]
