"""W006, against upstream's own `testE003E004W006` and the alert-side tests.

Upstream asserts counts only; the prefix is ours, read off
`TripDescriptorValidator.java:459`. Four of its tests assert the alert path in
passing, because the descriptor they reuse for E030, E031, E033 and E035 has no
trip_id and so warns once per informed_entity every time.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.upstream.w006 import check
from rulefixtures import entity, prefixes
from tripfixtures import SCHEDULED, alert, both, run, selector, td


def found(tmp_path: Path, *entities) -> list[str]:
    return prefixes(run(check, tmp_path, *entities))


def test_a_trip_with_no_trip_id_warns_once_per_carrier(tmp_path: Path) -> None:
    """Upstream, testE003E004W006's first stage: route_id `1` and no trip_id on
    a TripUpdate and a VehiclePosition, `expected.put(W006, 2)`."""
    assert len(found(tmp_path, both(td(route_id="1", schedule_relationship=SCHEDULED)))) == 2


def test_a_trip_with_a_trip_id_warns_about_nothing(tmp_path: Path) -> None:
    """Upstream, testE003E004W006's second stage: trip_id `1.1`."""
    assert found(tmp_path, both(td(trip_id="1.1", schedule_relationship=SCHEDULED))) == []


def test_an_informed_entity_whose_trip_has_no_trip_id_warns_once(tmp_path: Path) -> None:
    """Upstream, testE030, testE031, testE033 and testE035 all assert this in
    passing: one W006 per informed_entity that has a trip with no trip_id."""
    empty = td(schedule_relationship=SCHEDULED)
    one = selector(stop_id="1234", trip=empty)

    assert len(found(tmp_path, entity(alert=alert(one, one)))) == 2


# --- ours ----------------------------------------------------------------


def test_the_prefix_names_the_feed_entity_and_no_trip(tmp_path: Path) -> None:
    """Ours, read off `:459`. There is no trip_id to name, which is the whole
    finding, so the text is the entity id alone."""
    assert found(tmp_path, entity(trip_update={"trip": {}}, entity_id="E1")) == ["entity ID E1"]


def test_a_vehicle_position_with_no_trip_at_all_warns_about_nothing(tmp_path: Path) -> None:
    """Ours. The half is gated on `getVehicle().hasTrip()` at `:142`, so a
    VehiclePosition carrying no descriptor is not a descriptor with no
    trip_id."""
    assert found(tmp_path, entity(vehicle={"vehicle": {"id": "V1"}})) == []


def test_an_informed_entity_with_no_trip_at_all_warns_about_nothing(tmp_path: Path) -> None:
    """Ours. `:190` is inside `if (entitySelector.hasTrip())`, unlike the
    E035 call two lines above it."""
    assert found(tmp_path, entity(alert=alert(selector(stop_id="1234")))) == []


def test_an_empty_trip_id_counts_as_having_one(tmp_path: Path) -> None:
    """Ours. `hasTripId()` is proto2 presence, so a trip_id set to the empty
    string warns about nothing here, and is then looked up in `trips.txt` by the
    TripUpdate half as E003."""
    assert found(tmp_path, both(td(trip_id="", schedule_relationship=SCHEDULED))) == []
