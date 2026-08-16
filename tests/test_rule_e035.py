"""E035, against upstream's own `testE035`.

Upstream asserts counts only; the prefix is ours, read off
`TripDescriptorValidator.java:445`. Its feed is `bullrunner-gtfs.zip`, where
trip_id `1` belongs to route_id `A` and route `B` also exists;
`tripfixtures.feed_tables` carries both routes, because `checkE035` returns
early on a route_id that is in no `routes.txt` row and the three-occurrence case
would otherwise be unreachable.

This is the only check in the validator called from all three halves, which is
what makes that case three rather than two.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.upstream.e035 import check
from rulefixtures import ENTITY_ID, entity, prefixes
from tripfixtures import SCHEDULED, alert, run, selector, td

WRONG_ROUTE = (
    f"GTFS-rt entity ID {ENTITY_ID} trip_id 1 has route_id B but belongs to GTFS route_id A"
)


def found(tmp_path: Path, *entities) -> list[str]:
    return prefixes(run(check, tmp_path, *entities))


def everywhere(descriptor: dict[str, object]) -> dict[str, object]:
    """Upstream's own entity for this rule: the same descriptor on an alert
    informed_entity, a TripUpdate and a VehiclePosition at once."""
    return entity(
        trip_update={"trip": descriptor},
        vehicle={"trip": descriptor},
        alert=alert(selector(trip=descriptor)),
    )


def test_a_trip_with_neither_id_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE035's first stage: an alert selector with stop_id `1234`
    and an empty trip, whose only finding is W006."""
    empty = td(schedule_relationship=SCHEDULED)

    assert found(tmp_path, entity(alert=alert(selector(stop_id="1234", trip=empty)))) == []


def test_a_route_id_with_no_trip_id_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE035: a trip carrying route_id `A` and no trip_id. The
    condition needs both."""
    trip = td(route_id="A", schedule_relationship=SCHEDULED)

    assert found(tmp_path, entity(alert=alert(selector(stop_id="1234", trip=trip)))) == []


def test_a_trip_id_with_no_route_id_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE035: trip_id `1` on the alert, the TripUpdate and the
    VehiclePosition, `expected.clear()`."""
    trip = td(trip_id="1", schedule_relationship=SCHEDULED)

    assert found(tmp_path, everywhere(trip)) == []


def test_a_trip_id_on_its_own_route_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE035: trip_id `1` and route_id `A` on all three."""
    trip = td(trip_id="1", route_id="A", schedule_relationship=SCHEDULED)

    assert found(tmp_path, everywhere(trip)) == []


def test_a_trip_id_on_another_route_reports_three_times(tmp_path: Path) -> None:
    """Upstream, testE035: trip_id `1` and route_id `B` on all three,
    `expected.put(E035, 3)`. One entity, three occurrences, because `checkE035`
    is called from `:125`, `:174` and `:184`."""
    trip = td(trip_id="1", route_id="B", schedule_relationship=SCHEDULED)

    assert found(tmp_path, everywhere(trip)) == [WRONG_ROUTE] * 3


# --- ours ----------------------------------------------------------------


def test_the_prefix_names_the_feed_entity_and_both_route_ids(tmp_path: Path) -> None:
    """Ours, read off `:445`. It names `entity.getId()` rather than going
    through any of the trip text helpers, so all three call sites produce the
    same string for one entity."""
    trip = td(trip_id="1", route_id="B", schedule_relationship=SCHEDULED)

    assert found(tmp_path, entity(trip_update={"trip": trip}, entity_id="E1")) == [
        "GTFS-rt entity ID E1 trip_id 1 has route_id B but belongs to GTFS route_id A"
    ]


def test_a_route_id_that_is_in_no_gtfs_row_is_e004s_finding(tmp_path: Path) -> None:
    """Ours, the first early return at `:434`."""
    trip = td(trip_id="1", route_id="999", schedule_relationship=SCHEDULED)

    assert found(tmp_path, everywhere(trip)) == []


def test_a_trip_id_that_is_in_no_gtfs_row_is_e003s_finding(tmp_path: Path) -> None:
    """Ours, the second early return at `:439`."""
    trip = td(trip_id="100", route_id="B", schedule_relationship=SCHEDULED)

    assert found(tmp_path, everywhere(trip)) == []


def test_a_selector_with_no_trip_at_all_is_still_checked(tmp_path: Path) -> None:
    """Ours. `:184` is outside the `hasTrip()` guard, so the default
    TripDescriptor is handed in and `hasTripId()` short-circuits rather than
    anything failing."""
    assert found(tmp_path, entity(alert=alert(selector(stop_id="1234")))) == []
