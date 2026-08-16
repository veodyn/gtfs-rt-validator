"""E034, against upstream's own `testE034`.

Upstream asserts counts only; the prefix is ours, read off
`TripDescriptorValidator.java:419`. Upstream runs it against `testagency.zip`,
whose `agency_id` is `agency`, and `tripfixtures.feed_tables` carries an agency
with that id for the same reason.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.upstream.e034 import check
from rulefixtures import entity, prefixes
from tripfixtures import AGENCY_ID, SCHEDULED, alert, run, selector, td


def found(tmp_path: Path, *selectors) -> list[str]:
    return prefixes(run(check, tmp_path, entity(alert=alert(*selectors))))


def test_an_agency_id_that_is_in_the_gtfs_data_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE034's first stage: agency_id `agency`, `expected.clear()`."""
    assert found(tmp_path, selector(agency_id=AGENCY_ID)) == []


def test_an_agency_id_that_is_not_in_the_gtfs_data_reports_once(tmp_path: Path) -> None:
    """Upstream, testE034: agency_id `bad`, `expected.put(E034, 1)`. The prefix
    is ours."""
    assert found(tmp_path, selector(agency_id="bad")) == ["alert ID TEST_ENTITY agency_id bad"]


# --- ours ----------------------------------------------------------------


def test_a_selector_with_no_agency_id_reports_nothing(tmp_path: Path) -> None:
    """Ours. `hasAgencyId()` at `:417`, so an absent field is never compared
    against the empty string."""
    assert found(tmp_path, selector(stop_id="1234")) == []


def test_an_empty_agency_id_is_present_and_is_compared(tmp_path: Path) -> None:
    """Ours. proto2 presence, so an agency_id set to the empty string clears the
    guard and then fails the set membership."""
    assert found(tmp_path, selector(agency_id="")) == ["alert ID TEST_ENTITY agency_id "]


def test_only_alerts_are_examined(tmp_path: Path) -> None:
    """Ours. `checkE034` has one call site, `:183`, inside the alert half, and
    there is no agency_id anywhere on a TripDescriptor to check anyway."""
    trip = td(trip_id="1", schedule_relationship=SCHEDULED)

    assert found(tmp_path) == []
    assert prefixes(run(check, tmp_path, entity(trip_update={"trip": trip}))) == []


def test_every_informed_entity_is_examined(tmp_path: Path) -> None:
    """Ours. The check is inside the per-selector loop at `:181`."""
    assert len(found(tmp_path, selector(agency_id="bad"), selector(agency_id="worse"))) == 2
