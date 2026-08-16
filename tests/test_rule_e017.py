"""E017, an unchanged header timestamp across two iterations whose content changed.

`testE017` (`TimestampValidatorTest.java:526-601`) is upstream's, ported stage by
stage from the checkout at `jar-build/upstream/`. Its three stages move a trip_id
between the two iterations so the messages genuinely differ while the header
timestamp does not. Upstream asserts counts only; everything below
`UPSTREAM_CASES` is ours.

`testDuplicateFeedMessagesThrowException` (`:1151-1166`) is upstream's too, and
it is the one assertion in this cohort this project deliberately does not port
as written. See `test_two_identical_messages_report_rather_than_raise`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.times import MIN_POSIX_TIME
from gtfs_rt_validator.rules.upstream.e017 import RULE_ID, check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from rulefixtures import context, entity, message, occurrences, prefixes

NOW = Reading(MIN_POSIX_TIME * 1000, ClockSource.FIXED)


def an_iteration(header_timestamp: int, trip_id: str = "1.1") -> Msg:
    """One iteration in `testE017`'s shape: every timestamp equal, one trip."""
    return message(
        entity(
            trip_update={"trip": {"trip_id": trip_id}, "timestamp": header_timestamp},
            vehicle={"timestamp": header_timestamp},
        ),
        timestamp=header_timestamp,
    )


def found(tmp_path: Path, current: int, previous: int | None) -> list[str]:
    ctx = context(
        tmp_path,
        clock=NOW,
        previous=None if previous is None else an_iteration(previous, trip_id="1.2"),
    )
    return prefixes(check(an_iteration(current), ctx))


#: `testE017` in order: the current and previous header timestamps, with `None`
#: for no previous iteration, and the count upstream asserts.
UPSTREAM_CASES = (
    (MIN_POSIX_TIME, None, 0),
    (MIN_POSIX_TIME, MIN_POSIX_TIME, 1),
    (MIN_POSIX_TIME + 1, MIN_POSIX_TIME, 0),
)


@pytest.mark.parametrize(("current", "previous", "expected"), UPSTREAM_CASES)
def test_upstream_cases(tmp_path: Path, current: int, previous: int | None, expected: int) -> None:
    assert len(found(tmp_path, current, previous)) == expected


def test_the_prefix_names_the_repeated_timestamp(tmp_path: Path) -> None:
    """`:125`, the value alone."""
    assert found(tmp_path, MIN_POSIX_TIME, MIN_POSIX_TIME) == [
        f"header.timestamp of {MIN_POSIX_TIME}"
    ]


def test_a_previous_header_timestamp_of_zero_is_no_previous_at_all(tmp_path: Path) -> None:
    """`:120` tests the previous timestamp as well as the previous message. An
    unstamped earlier iteration is not "the same timestamp" as this one."""
    assert found(tmp_path, MIN_POSIX_TIME, 0) == []


def test_an_absent_current_header_timestamp_never_reaches_the_comparison(
    tmp_path: Path,
) -> None:
    """The whole previous-message chain lives in the `else` of `headerTimestamp
    == 0` (`:101-135`), so two unstamped iterations are W001 or E048, not E017."""
    ctx = context(tmp_path, clock=NOW, previous=message(entity()))

    assert prefixes(check(message(entity()), ctx)) == []


def test_a_decrease_is_e018_and_an_increase_is_w007(tmp_path: Path) -> None:
    """The chain is if/else-if (`:123-133`), so exactly one of the three fires."""
    assert found(tmp_path, MIN_POSIX_TIME, MIN_POSIX_TIME + 5) == []
    assert found(tmp_path, MIN_POSIX_TIME + 100, MIN_POSIX_TIME) == []


def test_a_non_posix_pair_is_still_compared(tmp_path: Path) -> None:
    """`:120-133` sits outside the `isPosix` branch, so two identical timestamps
    in milliseconds report here as well as under E001."""
    milliseconds = MIN_POSIX_TIME * 1000

    assert found(tmp_path, milliseconds, milliseconds) == [f"header.timestamp of {milliseconds}"]


def test_two_identical_messages_report_rather_than_raise(tmp_path: Path) -> None:
    """**No rule ports `testDuplicateFeedMessagesThrowException`, and by default
    nothing does.**

    Upstream throws `IllegalArgumentException` when the current and previous
    messages are equal (`:66-68`), and `BatchProcessor.java:263` does not catch
    it, so the run dies with no `.results.json` for that file or for any file
    after it. Reproducing that trades a complete report for none, so the chain
    runs and E017 fires, which is the finding the guard exists to keep
    meaningful. `runner/dedupe.py` reproduces the MD5 skip, so an ordinary
    byte-identical duplicate never reaches a rule at all.

    A compat run may ask for the abort with `cliargs.EQUAL_MESSAGE_ABORT_FLAG`,
    and it still does not happen here: `runner/equal_message.py` performs it from
    the loop, so this rule's answer to an equal pair is E017 either way.
    `tests/test_compat_equal_message_abort.py` owns the other half.
    """
    identical = an_iteration(MIN_POSIX_TIME)
    ctx = context(tmp_path, clock=NOW, previous=identical)

    assert prefixes(check(identical, ctx)) == [f"header.timestamp of {MIN_POSIX_TIME}"]


def test_the_occurrence_locates_the_header(tmp_path: Path) -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone."""
    ctx = context(tmp_path, clock=NOW, previous=an_iteration(MIN_POSIX_TIME, trip_id="1.2"))
    (one,) = occurrences(check(an_iteration(MIN_POSIX_TIME), ctx))

    assert (one.rule_id, one.context[ENTITY_PATH_KEY]) == (RULE_ID, "header")
