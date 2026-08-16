"""E031, against upstream's own `testE031`.

Upstream asserts counts only; the prefix is ours, read off
`TripDescriptorValidator.java:375`. Every stage of upstream's test also expects
one W006, because the descriptor it reuses never gets a trip_id.

This rule reads no static data at all: both sides of the comparison are on the
wire. What it shares with E030 is the gate at `:185`, which needs a route_id on
the selector *and* a trip on it.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.upstream.e031 import check
from rulefixtures import entity, prefixes
from tripfixtures import SCHEDULED, alert, run, selector, td

ROUTE_IDS_DIFFER = (
    "alert ID TEST_ENTITY informed_entity.route_id B does not equal informed_entity.trip.route_id A"
)


def found(tmp_path: Path, *selectors) -> list[str]:
    return prefixes(run(check, tmp_path, entity(alert=alert(*selectors))))


def test_a_selector_with_neither_route_id_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE031's first stage: stop_id `1234` and an empty trip."""
    empty = td(schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(stop_id="1234", trip=empty)) == []


def test_a_selector_route_id_with_no_trip_route_id_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE031: informed_entity.route_id `A` and a trip with none.
    The gate passes; `getTrip().hasRouteId()` at `:372` stops it."""
    empty = td(schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(stop_id="1234", route_id="A", trip=empty)) == []


def test_a_trip_route_id_with_no_selector_route_id_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE031: informed_entity.trip.route_id `A` and no
    informed_entity.route_id. The gate needs both, so the two are never compared
    even though one of them is plainly missing."""
    trip = td(route_id="A", schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(trip=trip)) == []


def test_two_route_ids_that_agree_report_nothing(tmp_path: Path) -> None:
    """Upstream, testE031: both `A`."""
    trip = td(route_id="A", schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(route_id="A", trip=trip)) == []


def test_two_route_ids_that_disagree_report_once(tmp_path: Path) -> None:
    """Upstream, testE031: informed_entity.route_id `B` against
    informed_entity.trip.route_id `A`, `expected.put(E031, 1)`. The prefix is
    ours, read off `:375`."""
    trip = td(route_id="A", schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(route_id="B", trip=trip)) == [ROUTE_IDS_DIFFER]


# --- ours ----------------------------------------------------------------


def test_neither_route_id_has_to_exist_in_the_gtfs_data(tmp_path: Path) -> None:
    """Ours. Nothing here consults `routes.txt`, so two ids that are in no
    `routes.txt` row still report when they differ. E004 would have caught them,
    except that E004 is never called for an alert."""
    trip = td(route_id="998", schedule_relationship=SCHEDULED)

    assert len(found(tmp_path, selector(route_id="999", trip=trip))) == 1


def test_every_informed_entity_is_examined(tmp_path: Path) -> None:
    """Ours. The check is inside the per-selector loop at `:181`."""
    trip = td(route_id="A", schedule_relationship=SCHEDULED)
    one = selector(route_id="B", trip=trip)

    assert len(found(tmp_path, one, one)) == 2
