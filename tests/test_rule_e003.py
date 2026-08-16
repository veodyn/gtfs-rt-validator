"""E003, against upstream's own `testE003E004W006` and `testE023`.

Every assertion marked "upstream" is transcribed from the real
`TripDescriptorValidatorTest.java` in the checkout at `jar-build/upstream/`,
not from a second-hand summary of it. Upstream asserts *counts* only, so
every assertion about occurrence text below is ours, read off
`TripDescriptorValidator.java:105` and `:153`.

The static feed is `tripfixtures.feed_tables`, which carries testagency's trips
`1.1` and `1.2` on route `1`; `100` and `100000000` are in no `trips.txt` row,
which is what upstream's own feed says about them too.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.upstream.e003 import check
from rulefixtures import entity, prefixes
from tripfixtures import ADDED, DUPLICATED, SCHEDULED, alert, both, run, selector, td


def found(tmp_path: Path, *entities) -> list[str]:
    return prefixes(run(check, tmp_path, *entities))


# --- upstream's own cases, stage by stage -----------------------------------


def test_a_trip_with_no_trip_id_is_w006_and_never_e003(tmp_path: Path) -> None:
    """Upstream, testE003E004W006: route_id `1` and no trip_id, `W006: 2` and no
    E003, because the trip lookup is the `else` of the W006 test."""
    assert found(tmp_path, both(td(route_id="1", schedule_relationship=SCHEDULED))) == []


def test_a_trip_id_that_is_in_the_gtfs_data_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE003E004W006: trip_id `1.1`, route_id `1`, `expected.clear()`."""
    descriptor = td(trip_id="1.1", route_id="1", schedule_relationship=SCHEDULED)

    assert found(tmp_path, both(descriptor)) == []


def test_a_trip_id_that_is_not_in_the_gtfs_data_reports_once_per_carrier(
    tmp_path: Path,
) -> None:
    """Upstream, testE003E004W006: trip_id `100`, `expected.put(E003, 2)`."""
    descriptor = td(trip_id="100", route_id="1", schedule_relationship=SCHEDULED)

    assert len(found(tmp_path, both(descriptor))) == 2


def test_an_added_trip_may_be_absent_from_the_gtfs_data(tmp_path: Path) -> None:
    """Upstream, testE003E004W006: the same trip_id with schedule_relationship
    ADDED, `expected.clear()`."""
    descriptor = td(trip_id="100", route_id="1", schedule_relationship=ADDED)

    assert found(tmp_path, both(descriptor)) == []


def test_a_valid_start_time_on_an_unknown_trip_is_e003_and_not_an_exception(
    tmp_path: Path,
) -> None:
    """Upstream, testE023's last stage: trip_id `100000000` with start_time
    `00:20:00` gives `E003: 2` and no E023, the regression for issue #217."""
    descriptor = td(trip_id="100000000", start_time="00:20:00", schedule_relationship=SCHEDULED)

    assert len(found(tmp_path, both(descriptor))) == 2


# --- the occurrence text, which upstream's test never looks at --------------


def test_the_trip_update_prefix_is_the_trip_id_text(tmp_path: Path) -> None:
    """Ours, read off `:105`: `GtfsUtils.getTripId(entity, tripUpdate)`."""
    descriptor = td(trip_id="100", schedule_relationship=SCHEDULED)

    assert found(tmp_path, entity(trip_update={"trip": descriptor})) == ["trip_id 100"]


def test_the_vehicle_prefix_is_built_inline_and_leaves_a_double_space(
    tmp_path: Path,
) -> None:
    """Ours, read off `:153`. The vehicle id is read through two unguarded
    getters, so a VehiclePosition with no vehicle descriptor, which is what
    `FeedMessageTest` builds, gives `vehicle_id ` and then nothing."""
    descriptor = td(trip_id="100", schedule_relationship=SCHEDULED)
    bare = entity(vehicle={"trip": descriptor})
    named = entity(vehicle={"trip": descriptor, "vehicle": {"id": "V1"}})

    assert found(tmp_path, bare) == ["vehicle_id  trip_id 100"]
    assert found(tmp_path, named) == ["vehicle_id V1 trip_id 100"]


def test_an_empty_trip_id_is_reported_from_the_trip_update_half_only(tmp_path: Path) -> None:
    """Ours. `hasTripId()` is true, so neither half reports W006; only the
    VehiclePosition half then tests `StringUtils.isEmpty` (`:148`)."""
    descriptor = td(trip_id="", schedule_relationship=SCHEDULED)

    assert found(tmp_path, both(descriptor)) == ["trip_id "]


def test_an_alert_is_never_examined_for_e003(tmp_path: Path) -> None:
    """Ours. Neither inline site is in the alert half, so an informed_entity
    naming a trip_id that exists nowhere in GTFS is not an E003."""
    descriptor = td(trip_id="100", schedule_relationship=SCHEDULED)

    assert found(tmp_path, entity(alert=alert(selector(trip=descriptor)))) == []


# --- the schedule_relationship enum gap -------------------------------------


def test_a_post_2015_schedule_relationship_does_not_exempt_a_missing_trip(
    tmp_path: Path,
) -> None:
    """Ours, and the reason compat decodes with the 2015 schema rather than
    masking. `isAddedTrip` reads `hasScheduleRelationship()` first, and
    protobuf 2.6.1 files DUPLICATED, which the 2015 enum does not have, in the
    unknown-field set. So the descriptor behaves as if the field were absent and
    E003 fires where ADDED would have exempted it."""
    duplicated = td(trip_id="100", schedule_relationship=DUPLICATED)
    added = td(trip_id="100", schedule_relationship=ADDED)

    assert found(tmp_path, both(duplicated)) == ["trip_id 100", "vehicle_id  trip_id 100"]
    assert found(tmp_path, both(added)) == []
