"""E018, a header timestamp that went backwards between two iterations.

`testE018` (`TimestampValidatorTest.java:603-672`) is upstream's, ported stage by
stage from the checkout at `jar-build/upstream/`. Its three stages hold the
current header at `MIN_POSIX_TIME + 1` and move the previous one either side of
it. Upstream asserts counts only; everything below `UPSTREAM_CASES` is ours.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.times import MIN_POSIX_TIME
from gtfs_rt_validator.rules.upstream.e018 import RULE_ID, check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from rulefixtures import context, entity, message, occurrences, prefixes

NOW = Reading(MIN_POSIX_TIME * 1000, ClockSource.FIXED)

#: `testE018`'s current iteration, fixed across all three of its stages.
CURRENT = MIN_POSIX_TIME + 1


def an_iteration(header_timestamp: int) -> Msg:
    return message(
        entity(
            trip_update={"trip": {"trip_id": "1.1"}, "timestamp": header_timestamp},
            vehicle={"timestamp": header_timestamp},
        ),
        timestamp=header_timestamp,
    )


def found(tmp_path: Path, previous: int | None, current: int = CURRENT) -> list[str]:
    ctx = context(
        tmp_path, clock=NOW, previous=None if previous is None else an_iteration(previous)
    )
    return prefixes(check(an_iteration(current), ctx))


#: `testE018` in order: the previous header timestamp, `None` for no previous
#: iteration, and the count upstream asserts.
UPSTREAM_CASES = (
    (None, 0),
    (MIN_POSIX_TIME, 0),
    (MIN_POSIX_TIME + 2, 1),
)


@pytest.mark.parametrize(("previous", "expected"), UPSTREAM_CASES)
def test_upstream_cases(tmp_path: Path, previous: int | None, expected: int) -> None:
    assert len(found(tmp_path, previous)) == expected


def test_the_prefix_names_both_timestamps(tmp_path: Path) -> None:
    """`:128`. The previous value is read back off the message rather than from
    the local one line above it; the two are the same value."""
    assert found(tmp_path, MIN_POSIX_TIME + 2) == [
        f"header.timestamp of {CURRENT} is less than the header.timestamp of {MIN_POSIX_TIME + 2}"
    ]


def test_an_equal_pair_is_e017_and_never_reaches_this_arm(tmp_path: Path) -> None:
    """The chain is if/else-if (`:123-133`)."""
    assert found(tmp_path, CURRENT) == []


def test_a_previous_header_timestamp_of_zero_is_no_previous_at_all(tmp_path: Path) -> None:
    """`:120`. Without that guard an unstamped earlier iteration would read as a
    decrease from 0 and report on every second file of a run."""
    assert found(tmp_path, 0) == []


def test_an_absent_current_header_timestamp_never_reaches_the_comparison(
    tmp_path: Path,
) -> None:
    ctx = context(tmp_path, clock=NOW, previous=an_iteration(MIN_POSIX_TIME))

    assert prefixes(check(message(entity()), ctx)) == []


def test_a_non_posix_pair_is_still_compared(tmp_path: Path) -> None:
    """`:120-133` sits outside the `isPosix` branch, so a decrease between two
    timestamps in milliseconds reports here as well as under E001."""
    milliseconds = MIN_POSIX_TIME * 1000

    expected = (
        f"header.timestamp of {milliseconds} is less than "
        f"the header.timestamp of {milliseconds + 5}"
    )

    assert found(tmp_path, milliseconds + 5, current=milliseconds) == [expected]


def test_the_occurrence_locates_the_header(tmp_path: Path) -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone."""
    ctx = context(tmp_path, clock=NOW, previous=an_iteration(MIN_POSIX_TIME + 2))
    (one,) = occurrences(check(an_iteration(CURRENT), ctx))

    assert (one.rule_id, one.context[ENTITY_PATH_KEY]) == (RULE_ID, "header")
