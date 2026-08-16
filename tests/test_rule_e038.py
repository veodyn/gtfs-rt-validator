"""E038, invalid `header.gtfs_realtime_version`.

Five of the assertions below are upstream's own, ported case by case from the
checkout at `jar-build/upstream/`, `gtfs-realtime-validator-lib/src/test/java/
edu/usf/cutr/gtfsrtvalidator/lib/test/rules/HeaderValidatorTest.java:43-91`
(`testE038`), rather than from a second-hand summary of it. Upstream
counts occurrences and never looks at a prefix, so every prefix assertion here
is ours.

One thing the port has to carry across: upstream's `FeedMessageTest` base class
leaves `feedMessageBuilder` holding one entity, id `TEST_ENTITY`, before any
test runs, and `testE038` never clears it. So each of upstream's five messages
carries that entity, and the builder is reused, which is why the FULL_DATASET
set in the second case is still set in the three after it. `feed()` below
states each message in full instead, so nothing depends on the order the tests
run in.

The absent-version branch of `isValidVersion` is not exercised here. It is
unreachable through a decode, because `gtfs_realtime_version` is `required` and
`proto/decode.py` refuses a header without it, exactly as protobuf-java does;
`tests/test_shared_versions.py` covers it against a hand-built header.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.upstream.e038 import RULE_ID, check

#: `FeedMessageTest.ENTITY_ID`, the id every message in upstream's test carries.
ENTITY_ID = "TEST_ENTITY"


def feed(header: dict[str, object], entities: Sequence[dict[str, object]] = ()) -> Msg:
    """One decoded `FeedMessage`, through the real encoder and decoder.

    The 2015 schema, which is the one upstream compiles against and the one
    `--compat` decodes with. Going through `encode` rather than building a `Msg`
    by hand is deliberate: a field name this schema does not declare raises here
    instead of quietly becoming a test that asserts nothing.
    """
    return decode(encode({"header": header, "entity": list(entities)}, V2015), V2015)


def occurrences(message: Msg) -> list:
    """What the rule found, as a list. `None` is the legal "nothing" too."""
    return list(check(message, None) or ())


def a_feed(version: str, **header: object) -> Msg:
    return feed({"gtfs_realtime_version": version, **header}, [{"id": ENTITY_ID}])


@pytest.mark.parametrize("version", ["1.0", "2.0"])
def test_a_valid_version_is_not_reported(version: str) -> None:
    """Upstream's first two cases. The second sets `incrementality` to keep E049
    quiet, which E038 neither reads nor is affected by; it is kept so the port
    stays case for case."""
    assert occurrences(a_feed(version, incrementality=0)) == []


@pytest.mark.parametrize("version", ["3.0", "1", "abcd"])
def test_an_invalid_version_is_reported_once(version: str) -> None:
    """Upstream's last three cases, each expecting exactly one E038."""
    found = occurrences(a_feed(version, incrementality=0))

    assert len(found) == 1
    assert found[0].rule_id == RULE_ID


def test_the_prefix_is_the_field_name_and_the_value() -> None:
    """`"header.gtfs_realtime_version of " + getGtfsRealtimeVersion()`,
    `HeaderValidator.java:52`. Ours: upstream asserts only the count."""
    (found,) = occurrences(a_feed("3.0"))

    assert found.prefix == "header.gtfs_realtime_version of 3.0"


def test_an_empty_version_is_invalid_and_renders_as_nothing_after_of() -> None:
    """A zero-length string is on the wire, so the field is present and fails
    the two equality tests. Java concatenates the empty string and leaves the
    prefix ending in a space, which is what a jar's report would show."""
    (found,) = occurrences(a_feed(""))

    assert found.prefix == "header.gtfs_realtime_version of "


def test_the_occurrence_locates_the_header_and_carries_the_value() -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone."""
    (found,) = occurrences(a_feed("3.0"))

    assert found.context[ENTITY_PATH_KEY] == "header"
    assert found.context["gtfsRealtimeVersion"] == "3.0"


def test_a_version_upstream_can_parse_is_still_reported() -> None:
    """`"3.0"` is v2 or higher and is not a valid version, so a feed can be
    reported for its version by this rule and checked for `incrementality` by
    E049 on the same message."""
    assert len(occurrences(a_feed("3.0"))) == 1
