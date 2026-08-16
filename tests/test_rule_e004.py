"""E004, against upstream's own `testE003E004W006`.

Upstream asserts counts only; the prefixes below are ours, read off
`TripDescriptorValidator.java:262` and `GtfsUtils.java:115-128`.

`tripfixtures.feed_tables` carries routes `1`, `2`, `3`, `A` and `B`, so `100`
is a route_id in no `routes.txt` row exactly as it is in upstream's testagency.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.upstream.e004 import check
from rulefixtures import entity, prefixes
from tripfixtures import SCHEDULED, alert, both, run, selector, td


def found(tmp_path: Path, *entities) -> list[str]:
    return prefixes(run(check, tmp_path, *entities))


def test_a_route_id_that_is_in_the_gtfs_data_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE003E004W006: trip_id `1.1` and route_id `1`, `expected.clear()`."""
    descriptor = td(trip_id="1.1", route_id="1", schedule_relationship=SCHEDULED)

    assert found(tmp_path, both(descriptor)) == []


def test_a_route_id_that_is_not_in_the_gtfs_data_reports_once_per_carrier(
    tmp_path: Path,
) -> None:
    """Upstream, testE003E004W006: route_id `100`, `expected.put(E004, 2)`."""
    descriptor = td(trip_id="1.1", route_id="100", schedule_relationship=SCHEDULED)

    assert len(found(tmp_path, both(descriptor))) == 2


def test_the_two_prefixes_name_the_route_and_the_vehicle(tmp_path: Path) -> None:
    """Ours. `getVehicleAndRouteId` gives `route_id X` for a TripUpdate and
    `vehicle_id V route_id X` for a VehiclePosition, both through unguarded
    getters, so a VehiclePosition with no vehicle descriptor leaves a double
    space."""
    descriptor = td(trip_id="1.1", route_id="100", schedule_relationship=SCHEDULED)
    named = entity(vehicle={"trip": descriptor, "vehicle": {"id": "V1"}})

    assert found(tmp_path, both(descriptor)) == ["route_id 100", "vehicle_id  route_id 100"]
    assert found(tmp_path, named) == ["vehicle_id V1 route_id 100"]


def test_an_absent_route_id_and_an_empty_one_are_the_same_thing_here(tmp_path: Path) -> None:
    """Ours. There is no `hasRouteId()` test: `StringUtils.isEmpty` covers both,
    which is what separates this rule from E035's `hasRouteId()`."""
    assert found(tmp_path, both(td(trip_id="1.1", schedule_relationship=SCHEDULED))) == []
    assert (
        found(tmp_path, both(td(trip_id="1.1", route_id="", schedule_relationship=SCHEDULED))) == []
    )


def test_an_alert_route_id_is_never_checked(tmp_path: Path) -> None:
    """Ours, and the trap this rule is best known for. `checkE004` has two call
    sites, `:123` and `:171`, and neither is in the alert half, so neither
    `informed_entity.route_id` nor `informed_entity.trip.route_id` reaches it."""
    unknown = td(trip_id="1", route_id="100", schedule_relationship=SCHEDULED)
    on_the_selector = entity(alert=alert(selector(route_id="100", trip=unknown)))

    assert found(tmp_path, on_the_selector) == []


def test_a_vehicle_position_with_no_trip_is_not_checked(tmp_path: Path) -> None:
    """Ours. The half is gated on `getVehicle().hasTrip()` (`:142`), so a
    VehiclePosition with no trip never reaches the unconditional call at `:171`."""
    assert found(tmp_path, entity(vehicle={"vehicle": {"id": "V1"}})) == []
