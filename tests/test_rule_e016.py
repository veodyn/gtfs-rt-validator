"""E016, against upstream's own `testE016`.

Upstream asserts counts only; the prefixes are ours, and they are E003's, since
the two rules are the two arms of one `if` and build their text the same two
ways (`:110` and `:158`).
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.upstream.e016 import check
from rulefixtures import entity, prefixes
from tripfixtures import ADDED, DUPLICATED, SCHEDULED, alert, both, run, selector, td


def found(tmp_path: Path, *entities) -> list[str]:
    return prefixes(run(check, tmp_path, *entities))


def test_a_scheduled_trip_that_is_in_the_gtfs_data_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE016: trip_id `1.1` with SCHEDULED, `expected.clear()`."""
    assert found(tmp_path, both(td(trip_id="1.1", schedule_relationship=SCHEDULED))) == []


def test_an_added_trip_that_is_not_in_the_gtfs_data_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE016: trip_id `100` with ADDED, `expected.clear()`. That
    one is E003's business, and E003 exempts it."""
    assert found(tmp_path, both(td(trip_id="100", schedule_relationship=ADDED))) == []


def test_an_added_trip_that_is_in_the_gtfs_data_reports_once_per_carrier(
    tmp_path: Path,
) -> None:
    """Upstream, testE016: trip_id `1.1` with ADDED, `expected.put(E016, 2)`."""
    assert len(found(tmp_path, both(td(trip_id="1.1", schedule_relationship=ADDED)))) == 2


def test_the_two_prefixes_are_e003s(tmp_path: Path) -> None:
    """Ours, read off `:110` and `:158`."""
    added = td(trip_id="1.1", schedule_relationship=ADDED)
    named = entity(vehicle={"trip": added, "vehicle": {"id": "V1"}})

    assert found(tmp_path, both(added)) == ["trip_id 1.1", "vehicle_id  trip_id 1.1"]
    assert found(tmp_path, named) == ["vehicle_id V1 trip_id 1.1"]


def test_a_post_2015_schedule_relationship_is_not_an_added_trip(tmp_path: Path) -> None:
    """Ours, the mirror of E003's enum-gap case. DUPLICATED is not in the 2015
    enum, so `hasScheduleRelationship()` is false, `isAddedTrip` is false and
    this rule stays quiet on a trip that is in the GTFS data."""
    duplicated = td(trip_id="1.1", schedule_relationship=DUPLICATED)

    assert found(tmp_path, both(duplicated)) == []


def test_an_alert_is_never_examined_for_e016(tmp_path: Path) -> None:
    """Ours. Both sites are in the two vehicle-bearing halves."""
    added = td(trip_id="1.1", schedule_relationship=ADDED)

    assert found(tmp_path, entity(alert=alert(selector(trip=added)))) == []
