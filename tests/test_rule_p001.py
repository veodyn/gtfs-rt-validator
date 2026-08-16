"""P001: a header that declares a GTFS-Realtime version below 2.0.

The rule's whole difficulty is not firing where E038 already does, so the tests
below are mostly about silence. E038 reports a version that is neither `"1.0"`
nor `"2.0"` by string equality, which means `"1.00"`, `"0.9"` and `" 1.0"` are
all already somebody's finding even though every one of them is numerically
below 2.0. P001 defers to that check, so its only finding is `"1.0"`.

Everything here is 2015-visible: `gtfs_realtime_version` is `required` at both
pins. What the jar has to say about a v1.0 header is nothing at all: E038
accepts `"1.0"`, and E048 and E049 both need v2, so a v1.0 header with no
timestamp would be W001's rather than E048's. The fixtures state a timestamp and
an `incrementality` anyway, so no upstream rule has anything to say about them.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.practice.p001 import check
from specfixtures import context, message, occurrences, prefixes

INCREMENTALITY = SCHEMA.enums["FeedHeader.Incrementality"]["FULL_DATASET"]

REPORTED = "header.gtfs_realtime_version of 1.0 is below the 2.0 the practice recommends"


def run(version: str = "1.0"):
    return check(
        message(version=version, timestamp=1_700_000_000, incrementality=INCREMENTALITY),
        context(),
    )


def test_a_version_one_header_is_reported():
    assert prefixes(run("1.0")) == [REPORTED]


def test_a_version_two_header_is_silent():
    """The conformant twin, and the only difference is the four bytes."""
    assert prefixes(run("2.0")) == []


def test_at_most_one_occurrence_because_the_header_is_one_field():
    assert len(occurrences(run("1.0"))) == 1


@pytest.mark.parametrize("version", ["1.00", "0.9", "1.5", " 1.0", "1"])
def test_a_version_e038_rejects_is_e038s_finding_and_not_this_ones(version: str):
    """Every one of these is numerically below 2.0 and every one of them is
    silent here, because `is_valid_version` is string equality against `"1.0"`
    and `"2.0"` and E038 has already reported each. Reporting the same header
    field twice for the same reason is what this rule must not do."""
    assert prefixes(run(version)) == []


@pytest.mark.parametrize("version", ["abc", "", "2.0f", "NaN"])
def test_a_version_that_is_not_a_number_is_never_asked_the_numeric_question(version: str):
    """ "Numerically below 2.0" has no answer for `"abc"`. The validity gate runs
    first, so the parse is never reached and nothing here can raise."""
    assert prefixes(run(version)) == []


@pytest.mark.parametrize("version", ["3.0", "10.0"])
def test_a_version_above_two_that_e038_also_rejects_is_silent(version: str):
    """The other side of the same gate: `"3.0"` is v2-or-higher *and* an invalid
    version, which `_shared/versions.py` records as the reason its two helpers
    are not each other's negation."""
    assert prefixes(run(version)) == []


def test_the_occurrence_locates_the_header_and_carries_the_version():
    found = occurrences(run("1.0"))

    assert [one.rule_id for one in found] == ["P001"]
    assert [one.context["entityPath"] for one in found] == ["header"]
    assert [one.context["gtfsRealtimeVersion"] for one in found] == ["1.0"]
