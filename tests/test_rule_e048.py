"""E048, a v2.0-or-higher header with no timestamp, and the `catch` that widens it.

`testE048` (`TimestampValidatorTest.java:102-137`) is upstream's, ported stage by
stage from the checkout at `jar-build/upstream/`. It asserts counts only, and it
never exercises the `catch`: everything below `UPSTREAM_CASES` is ours.

The `catch` is the point of the rule. `TimestampValidator.java:88-93` sets the
flag to `true` before calling `GtfsUtils.isV2orHigher`, so a version that
`Float.parseFloat` refuses leaves it true and E048 fires. `HeaderValidator.java`
`:60-62` catches the identical exception with no such flag and skips E049
instead. A port whose version helper answered a tidy `False` would get W001 here
and lose E048 entirely, which is why `_shared/versions.is_v2_or_higher` raises.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.times import MIN_POSIX_TIME
from gtfs_rt_validator.rules.upstream.e048 import RULE_ID, check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from rulefixtures import context, entity, message, occurrences, prefixes

NOW = Reading(MIN_POSIX_TIME * 1000, ClockSource.FIXED)


def a_feed(header_timestamp: int | None = None, version: str = "2.0") -> Msg:
    """`testE048`'s entity, whose own timestamps are W001's business, not this rule's."""
    header: dict[str, object] = {}
    if header_timestamp is not None:
        header["timestamp"] = header_timestamp
    return message(
        entity(trip_update={"trip": {}}, vehicle={"vehicle": {}}), version=version, **header
    )


#: `testE048` in order: the header timestamp, and the count upstream asserts.
UPSTREAM_CASES = ((None, 1), (MIN_POSIX_TIME, 0))


@pytest.mark.parametrize(("header_timestamp", "expected"), UPSTREAM_CASES)
def test_upstream_cases(tmp_path: Path, header_timestamp: int | None, expected: int) -> None:
    feed = a_feed(header_timestamp)

    assert len(occurrences(check(feed, context(tmp_path, clock=NOW)))) == expected


def test_the_prefix_is_empty(tmp_path: Path) -> None:
    """`RuleUtils.addOccurrence(E048, "", ...)`, `:96`. The whole message a
    reader sees is the rule's suffix, which lives in the manifest."""
    (found,) = occurrences(check(a_feed(), context(tmp_path, clock=NOW)))

    assert (found.rule_id, found.prefix) == (RULE_ID, "")
    assert found.context[ENTITY_PATH_KEY] == "header"


def test_a_v1_header_reports_nothing_here(tmp_path: Path) -> None:
    """The W001 arm of the fork. `tests/test_rule_w001.py` holds its counts."""
    assert prefixes(check(a_feed(version="1.0"), context(tmp_path, clock=NOW))) == []


def test_a_version_above_two_still_counts_as_v2_or_higher(tmp_path: Path) -> None:
    """`isV2orHigher` is `>= 2.0f`, not an equality, so `"3.0"` fires here as
    well as failing E038. The two rules ask different questions of one field."""
    assert len(occurrences(check(a_feed(version="3.0"), context(tmp_path, clock=NOW)))) == 1


@pytest.mark.parametrize("version", ["abcd", "", "  ", "1,0", "2.0 f"])
def test_a_version_java_cannot_parse_reports_e048_and_not_w001(
    tmp_path: Path, version: str
) -> None:
    """`:88-93`. This is the half `HeaderValidator` gets the other way round."""
    feed = a_feed(version=version)

    assert len(occurrences(check(feed, context(tmp_path, clock=NOW)))) == 1


def test_the_float32_boundary_is_javas_and_not_pythons(tmp_path: Path) -> None:
    """`Float.parseFloat("1.99999999")` is exactly 2.0f, so upstream calls that
    header v2 where a port through Python's `float()` would call it v1 and
    report W001 instead. `tests/test_shared_versions.py` measures the parse."""
    assert len(occurrences(check(a_feed(version="1.99999999"), context(tmp_path, clock=NOW)))) == 1
    assert occurrences(check(a_feed(version="1.9999999"), context(tmp_path, clock=NOW))) == []


def test_an_explicit_zero_header_timestamp_is_the_same_as_an_absent_one(tmp_path: Path) -> None:
    """`:86` is `getTimestamp()` with no `has` test, so the two are one case."""
    assert len(occurrences(check(a_feed(0), context(tmp_path, clock=NOW)))) == 1
