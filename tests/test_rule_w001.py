"""W001, a timestamp that is not populated. Three sites, one rule.

`testW001` (`TimestampValidatorTest.java:49-97`) and the W001 half of `testE048`
(`:102-137`) are upstream's, ported stage by stage from the checkout at
`jar-build/upstream/` rather than from a second-hand summary.
Upstream counts occurrences and never looks at a prefix here, so everything
below `UPSTREAM_*` is ours.

The header site is the interesting one: it fires only when the header timestamp
is absent **and** the version parses below 2.0. An absent or unparseable version
logs E048 instead, because `TimestampValidator.java:88-93` pre-initialises its
flag to `true` and the `catch` leaves it there. `tests/test_rule_e048.py` holds
the other half of that fork.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.errors import DecodeError
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.times import MIN_POSIX_TIME
from gtfs_rt_validator.rules.upstream.w001 import RULE_ID, check
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from rulefixtures import ENTITY_ID, context, entity, message, occurrences, prefixes

#: `TimestampValidatorTest`'s own current time throughout: `MIN_POSIX_TIME`.
NOW = Reading(MIN_POSIX_TIME * 1000, ClockSource.FIXED)


def a_feed(
    header_timestamp: int | None = None,
    trip_update_timestamp: int | None = None,
    vehicle_timestamp: int | None = None,
    version: str = "1.0",
) -> Msg:
    """`testW001`'s one entity: an empty TripDescriptor and an empty VehicleDescriptor.

    Upstream sets `vehiclePositionBuilder.setVehicle(VehicleDescriptor.newBuilder())`,
    an empty descriptor, so the id it reads is the empty string.
    """
    trip_update: dict[str, object] = {"trip": {}}
    vehicle: dict[str, object] = {"vehicle": {}}
    if trip_update_timestamp is not None:
        trip_update["timestamp"] = trip_update_timestamp
    if vehicle_timestamp is not None:
        vehicle["timestamp"] = vehicle_timestamp
    header: dict[str, object] = {}
    if header_timestamp is not None:
        header["timestamp"] = header_timestamp
    return message(entity(trip_update=trip_update, vehicle=vehicle), version=version, **header)


#: `testW001` in order: header, TripUpdate and VehiclePosition timestamps, then
#: the count upstream asserts. A v1.0 header throughout.
UPSTREAM_W001 = (
    (None, None, None, 3),
    (MIN_POSIX_TIME, None, None, 2),
    (MIN_POSIX_TIME, MIN_POSIX_TIME, None, 1),
    (MIN_POSIX_TIME, MIN_POSIX_TIME, MIN_POSIX_TIME, 0),
)

#: `testE048`, the same shape with a v2.0 header. The header site never fires
#: there, so two entity warnings survive an absent header timestamp.
UPSTREAM_E048 = (
    (None, None, None, 2),
    (MIN_POSIX_TIME, None, None, 2),
)


@pytest.mark.parametrize(("header", "trip_update", "vehicle", "expected"), UPSTREAM_W001)
def test_upstream_w001_cases(
    tmp_path: Path, header: int | None, trip_update: int | None, vehicle: int | None, expected: int
) -> None:
    found = occurrences(check(a_feed(header, trip_update, vehicle), context(tmp_path, clock=NOW)))

    assert len(found) == expected


@pytest.mark.parametrize(("header", "trip_update", "vehicle", "expected"), UPSTREAM_E048)
def test_upstream_e048_cases_still_warn_about_the_entities(
    tmp_path: Path, header: int | None, trip_update: int | None, vehicle: int | None, expected: int
) -> None:
    feed = a_feed(header, trip_update, vehicle, version="2.0")

    assert len(occurrences(check(feed, context(tmp_path, clock=NOW)))) == expected


def test_the_three_prefixes_name_the_header_the_trip_and_the_vehicle(tmp_path: Path) -> None:
    """`:99`, `:148` and `:274`. The header's is the bare literal `"header"`;
    the TripUpdate's is `GtfsUtils.getTripId`, which falls back to the entity id
    when the descriptor carries no trip_id; the VehiclePosition's is built
    inline from `getVehicle().getId()` with no presence guard at either step, so
    an empty descriptor gives a trailing space rather than the entity id."""
    found = prefixes(check(a_feed(), context(tmp_path, clock=NOW)))

    assert found == ["header", f"entity ID {ENTITY_ID}", "vehicle_id "]


def test_a_trip_id_is_used_when_the_descriptor_has_one(tmp_path: Path) -> None:
    feed = message(entity(trip_update={"trip": {"trip_id": "1.1"}}))

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == ["header", "trip_id 1.1"]


def test_the_occurrences_locate_the_header_and_each_entity(tmp_path: Path) -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone."""
    found = occurrences(check(a_feed(), context(tmp_path, clock=NOW)))

    assert [one.context[ENTITY_PATH_KEY] for one in found] == [
        "header",
        "entity[0].trip_update",
        "entity[0].vehicle",
    ]


@pytest.mark.parametrize("version", ["2.0", "3.0"])
def test_a_v2_header_reports_e048_rather_than_w001(tmp_path: Path, version: str) -> None:
    feed = message(entity(), version=version)

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == []


@pytest.mark.parametrize("version", ["abcd", "", "  ", "1,0"])
def test_a_version_java_cannot_parse_reports_e048_rather_than_w001(
    tmp_path: Path, version: str
) -> None:
    """`:88-93`: the flag is `true` before the `try`, and the `catch` leaves it
    there. A helper that answered "not v2" for junk would report W001 here,
    which is one occurrence upstream never writes and one it does."""
    feed = message(entity(), version=version)

    assert prefixes(check(feed, context(tmp_path, clock=NOW))) == []


def test_a_version_absent_from_the_wire_never_reaches_the_rule_at_all(tmp_path: Path) -> None:
    """The one case the fork cannot be asked about, measured rather than assumed.

    `FeedHeader.gtfs_realtime_version` is `required` at both pins, so a message
    without it fails `isInitialized` and never becomes a `Msg`. Upstream is the
    same: `FeedMessage.parseFrom` throws `InvalidProtocolBufferException` and
    `BatchProcessor.java:238-241` skips the file with no results written. So the
    reachable trigger for the E048 arm is a version that is present and
    unparseable, `""` included, and never a truly absent one.
    """
    body = {"header": {"timestamp": MIN_POSIX_TIME}, "entity": [{"id": ENTITY_ID}]}

    with pytest.raises(DecodeError, match="gtfs_realtime_version"):
        decode(encode(body, V2015), V2015)

    assert prefixes(check(a_feed(MIN_POSIX_TIME), context(tmp_path, clock=NOW))) == [
        f"entity ID {ENTITY_ID}",
        "vehicle_id ",
    ]


def test_the_rule_reports_its_own_id(tmp_path: Path) -> None:
    (found, *_) = occurrences(check(a_feed(), context(tmp_path, clock=NOW)))

    assert found.rule_id == RULE_ID
