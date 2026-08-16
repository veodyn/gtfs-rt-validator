"""E030, against upstream's own `testE030`.

Upstream asserts counts only; the prefix is ours, read off
`TripDescriptorValidator.java:356`.

Upstream runs this against `bullrunner-gtfs.zip`, where trip_id `1` belongs to
route_id `A`, and `tripfixtures.feed_tables` carries exactly that pair. Its
stages each rebuild one `informed_entity`, so each test below builds one
selector.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.upstream.e030 import check
from rulefixtures import entity, prefixes
from tripfixtures import SCHEDULED, alert, run, selector, td

WRONG_ROUTE = (
    "alert ID TEST_ENTITY informed_entity.trip.trip_id 1 does not belong to "
    "informed_entity.route_id B (GTFS says it belongs to route_id A)"
)


def found(tmp_path: Path, *selectors) -> list[str]:
    return prefixes(run(check, tmp_path, entity(alert=alert(*selectors))))


def test_a_selector_with_neither_id_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE030's first stage: stop_id `1234` and an empty trip, whose
    only finding is W006. The gate at `:185` needs a route_id on the selector."""
    empty = td(schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(stop_id="1234", trip=empty)) == []


def test_a_trip_id_with_no_selector_route_id_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE030: trip_id `1` and no informed_entity.route_id,
    `expected.clear()`. Half the gate is missing, so neither E030 nor E031
    runs."""
    trip = td(trip_id="1", schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(stop_id="1234", trip=trip)) == []


def test_a_selector_route_id_with_no_trip_id_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE030: informed_entity.route_id `A` and a trip with no
    trip_id, whose only finding is W006. The gate passes and `hasTripId()`
    inside `checkE030` stops it."""
    empty = td(schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(stop_id="1234", route_id="A", trip=empty)) == []


def test_a_trip_id_that_belongs_to_the_selectors_route_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE030: route_id `A` and trip_id `1`, `expected.clear()`."""
    trip = td(trip_id="1", schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(route_id="A", trip=trip)) == []


def test_a_trip_id_that_belongs_to_another_route_reports_once(tmp_path: Path) -> None:
    """Upstream, testE030: route_id `B` and trip_id `1`, `expected.put(E030, 1)`.
    The prefix is ours, read off `:356`."""
    trip = td(trip_id="1", schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(route_id="B", trip=trip)) == [WRONG_ROUTE]


# --- ours ----------------------------------------------------------------


def test_a_trip_id_that_is_in_no_gtfs_row_reports_nothing(tmp_path: Path) -> None:
    """Ours. `gtfsTrip != null` is tested before the comparison, so an unknown
    trip_id on an alert is nobody's finding here: E003 is not called for alerts
    either."""
    trip = td(trip_id="100", schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(route_id="B", trip=trip)) == []


def test_the_route_id_compared_is_the_selectors_and_not_the_trips(tmp_path: Path) -> None:
    """Ours. `:351` reads `entitySelector.getRouteId()`, so a trip carrying its
    own contradicting route_id changes nothing here; that pair is E031's."""
    trip = td(trip_id="1", route_id="B", schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(route_id="A", trip=trip)) == []


def test_every_informed_entity_is_examined(tmp_path: Path) -> None:
    """Ours. The check is inside the per-selector loop at `:181`."""
    trip = td(trip_id="1", schedule_relationship=SCHEDULED)
    one = selector(route_id="B", trip=trip)

    assert len(found(tmp_path, one, one)) == 2
