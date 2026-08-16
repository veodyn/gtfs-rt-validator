"""E049, a v2-or-higher header with no `incrementality`.

Three of the assertions below are upstream's own, ported case by case from the
checkout at `jar-build/upstream/`, `gtfs-realtime-validator-lib/src/test/java/
edu/usf/cutr/gtfsrtvalidator/lib/test/rules/HeaderValidatorTest.java:161-193`
(`testE049`), rather than from a second-hand summary of it. Upstream
counts occurrences and never looks at a prefix, so the empty-prefix assertion is
ours, as is everything below `UPSTREAM_CASES`.

The half upstream never tests, and the half this file exists for, is the one at
`HeaderValidator.java:60-62`: `isV2orHigher` hands the version straight to
`Float.parseFloat` with no `has` guard, so a version that is absent or not a
number throws, the `catch` logs it, and **E049 is skipped**. `TimestampValidator`
`:87-100` catches the identical failure with its flag already set to true and
therefore logs E048. Both halves are compat surface, so a version of `"abcd"`
producing nothing here is the rule working, not the rule giving up.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.upstream.e049 import RULE_ID, check

#: `FeedMessageTest.ENTITY_ID`, the id every message in upstream's test carries.
ENTITY_ID = "TEST_ENTITY"

FULL_DATASET = 0
DIFFERENTIAL = 1

#: `testE049` in order: version, the incrementality the header carries or `None`
#: for a header that does not mention it, and the number upstream asserts.
UPSTREAM_CASES: tuple[tuple[str, int | None, int], ...] = (
    ("1.0", None, 0),
    ("2.0", None, 1),
    ("2.0", FULL_DATASET, 0),
)


def feed(header: dict[str, object], entities: Sequence[dict[str, object]] = ()) -> Msg:
    """One decoded `FeedMessage`, through the real encoder and decoder.

    The 2015 schema, which is the one upstream compiles against and the one
    `--compat` decodes with.
    """
    return decode(encode({"header": header, "entity": list(entities)}, V2015), V2015)


def occurrences(message: Msg) -> list:
    """What the rule found, as a list. `None` is the legal "nothing" too."""
    return list(check(message, None) or ())


def a_feed(version: str, incrementality: int | None = None) -> Msg:
    header: dict[str, object] = {"gtfs_realtime_version": version}
    if incrementality is not None:
        header["incrementality"] = incrementality
    return feed(header, [{"id": ENTITY_ID}])


@pytest.mark.parametrize(("version", "incrementality", "expected"), UPSTREAM_CASES)
def test_upstream_cases(version: str, incrementality: int | None, expected: int) -> None:
    assert len(occurrences(a_feed(version, incrementality))) == expected


def test_the_prefix_is_empty() -> None:
    """`RuleUtils.addOccurrence(E049, "", ...)`, `HeaderValidator.java:58`. The
    whole message a reader sees is the rule's suffix, which lives in the
    manifest; nothing varies per occurrence, and nothing is invented to fill the
    gap."""
    (found,) = occurrences(a_feed("2.0"))

    assert found.rule_id == RULE_ID
    assert found.prefix == ""


def test_the_occurrence_locates_the_header() -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone."""
    (found,) = occurrences(a_feed("2.0"))

    assert found.context[ENTITY_PATH_KEY] == "header"


def test_an_explicit_differential_counts_as_populated() -> None:
    """The test is `hasIncrementality()`, not which value it holds."""
    assert occurrences(a_feed("2.0", DIFFERENTIAL)) == []


def test_a_version_above_two_is_still_asked_for_incrementality() -> None:
    """`isV2orHigher` is a `>= 2.0f` comparison, not an equality, so `"3.0"`
    fires here as well as failing E038. The two rules answer different
    questions about the same field."""
    assert len(occurrences(a_feed("3.0"))) == 1


#: Non-ASCII decimal digits, which `Float.parseFloat` refuses. Measured on JDK
#: 17: all three throw `NumberFormatException`, so the jar skips E049 on a feed
#: carrying one and this rule must report nothing rather than one occurrence.
UNICODE_DIGIT_VERSIONS = ("\u0662.\u0660", "\uff12.\uff10", "\u0968.\u0966")


@pytest.mark.parametrize("version", ["abcd", "", "  ", "1,0", "2.0 f", *UNICODE_DIGIT_VERSIONS])
def test_a_version_java_cannot_parse_skips_the_rule_entirely(version: str) -> None:
    """The catch at `HeaderValidator.java:60-62`. None of these headers carries
    an incrementality, so a rule that answered "not v2" instead of raising, or
    that let the failure through, would be visible here as one occurrence
    instead of none."""
    assert occurrences(a_feed(version)) == []


@pytest.mark.parametrize("version", ["0x1p1024", "0x1p2000", "1e400", "3.4e39"])
def test_a_version_that_overflows_to_infinity_is_reported_not_skipped(version: str) -> None:
    """Measured on JDK 17: every one of these prints "Infinity" and compares
    `>= 2.0f` as true, so the jar reaches the `hasIncrementality` test and logs
    one E049. The hex rows are the ones that matter: `float.fromhex` raises
    `OverflowError` past the double range where `float()` returns infinity, so a
    port that forwards it aborts the whole run on a feed the jar reports."""
    assert len(occurrences(a_feed(version))) == 1


@pytest.mark.parametrize("version", ["-0x1p1024", "-1e400", "-3.4e39"])
def test_a_version_that_overflows_negative_is_not_v2(version: str) -> None:
    """The same overflow with a sign: Java prints "-Infinity", which is below
    2.0f, so the rule is answered "not v2" rather than raising or aborting."""
    assert occurrences(a_feed(version)) == []


def test_the_float32_boundary_is_javas_and_not_pythons() -> None:
    """`Float.parseFloat("1.99999999")` is exactly 2.0f, so upstream calls that
    feed v2 where a port through Python's `float()` would call it v1 and report
    nothing. `tests/test_shared_versions.py` measures the parse against JDK 17;
    this asserts that the rule is reading it."""
    assert len(occurrences(a_feed("1.99999999"))) == 1
    assert occurrences(a_feed("1.9999999")) == []
