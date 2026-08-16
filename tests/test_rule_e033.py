"""E033, against upstream's own `testE033`.

Upstream asserts counts only; the prefix is ours, read off
`TripDescriptorValidator.java:402`, including the doubled "not not" that is in
the source there.

The condition is two nested tests. The outer one lists the selector's own
specifiers, and `trip` is deliberately not among them; the inner one then asks
whether the trip is absent or carries neither a trip_id nor a route_id.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.upstream.e033 import check
from rulefixtures import entity, prefixes
from tripfixtures import AGENCY_ID, SCHEDULED, alert, run, selector, td

NOTHING_SPECIFIED = (
    "alert ID TEST_ENTITY informed_entity and informed_entity.trip "
    "do not not reference any agency, route, trip, or stop"
)


def found(tmp_path: Path, *selectors) -> list[str]:
    return prefixes(run(check, tmp_path, entity(alert=alert(*selectors))))


def test_an_informed_entity_with_nothing_in_it_reports_once(tmp_path: Path) -> None:
    """Upstream, testE033's first and last stages, `expected.put(E033, 1)`. The
    prefix is ours, and the doubled "not not" is upstream's."""
    assert found(tmp_path, selector()) == [NOTHING_SPECIFIED]


def test_a_stop_id_is_a_specifier(tmp_path: Path) -> None:
    """Upstream, testE033: stop_id `1234`, `expected.clear()`."""
    assert found(tmp_path, selector(stop_id="1234")) == []


def test_a_route_id_is_a_specifier(tmp_path: Path) -> None:
    """Upstream, testE033: informed_entity.route_id `A`."""
    assert found(tmp_path, selector(route_id="A")) == []


def test_an_agency_id_is_a_specifier(tmp_path: Path) -> None:
    """Upstream, testE033: agency_id `agency`, run against testagency."""
    assert found(tmp_path, selector(agency_id=AGENCY_ID)) == []


def test_a_route_type_is_a_specifier(tmp_path: Path) -> None:
    """Upstream, testE033: route_type 0. proto2 presence, so the zero counts."""
    assert found(tmp_path, selector(route_type=0)) == []


def test_a_trip_id_inside_the_trip_is_a_specifier(tmp_path: Path) -> None:
    """Upstream, testE033: a trip carrying trip_id `1` and nothing on the
    selector itself, `expected.clear()`."""
    trip = td(trip_id="1", schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(trip=trip)) == []


def test_a_route_id_inside_the_trip_is_a_specifier_too(tmp_path: Path) -> None:
    """Upstream, testE033: a trip carrying only route_id `A`, whose finding is
    W006 rather than E033."""
    trip = td(route_id="A", schedule_relationship=SCHEDULED)

    assert found(tmp_path, selector(trip=trip)) == []


# --- ours ----------------------------------------------------------------


def test_a_selector_carrying_only_an_empty_trip_reports(tmp_path: Path) -> None:
    """Ours. `trip` is not in the outer list of specifiers, so an empty trip
    sub-message does not save the selector, and the inner test then finds
    neither id on it."""
    assert found(tmp_path, selector(trip=td(schedule_relationship=SCHEDULED))) == [
        NOTHING_SPECIFIED
    ]


def test_every_informed_entity_is_examined(tmp_path: Path) -> None:
    """Ours. Upstream's test replaces its one selector each stage; the check
    itself is inside the per-selector loop at `:181`."""
    assert found(tmp_path, selector(), selector(stop_id="1234"), selector()) == [
        NOTHING_SPECIFIED,
        NOTHING_SPECIFIED,
    ]
