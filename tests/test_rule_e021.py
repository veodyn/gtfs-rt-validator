"""E021, against upstream's own `testE021`.

Upstream asserts counts only; the prefixes are ours, read off
`TripDescriptorValidator.java:316`.

**The resolver is SMART, not STRICT**: reading `parseStrict()` as resolver
strictness is the mistake, and it is an easy one. `_shared/timeformats.is_valid_date_format` records the JDK 17.0.19
measurement; what is pinned here is that this rule is its caller and therefore
inherits it, because a reader who assumed February 30th were rejected would
change the wrong file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.rules.upstream.e021 import check
from rulefixtures import entity, prefixes
from tripfixtures import SCHEDULED, both, run, td


def found(tmp_path: Path, *entities) -> list[str]:
    return prefixes(run(check, tmp_path, *entities))


def test_no_start_date_at_all_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE021's first stage. The `hasStartDate()` test is inside the
    helper (`:314`) rather than at the two call sites, which is why the dispatch
    calls this one unconditionally."""
    assert found(tmp_path, both(td(trip_id="1.1", schedule_relationship=SCHEDULED))) == []


def test_a_valid_start_date_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE021: `20170101`, `expected.clear()`."""
    descriptor = td(trip_id="1.1", start_date="20170101", schedule_relationship=SCHEDULED)

    assert found(tmp_path, both(descriptor)) == []


def test_an_invalid_start_date_reports_once_per_carrier(tmp_path: Path) -> None:
    """Upstream, testE021: `01-01-2017`, `expected.put(E021, 2)`."""
    descriptor = td(trip_id="1.1", start_date="01-01-2017", schedule_relationship=SCHEDULED)

    assert len(found(tmp_path, both(descriptor))) == 2


@pytest.mark.parametrize("start_date", ["20170230", "20170229", "20170431"])
def test_an_impossible_calendar_date_is_accepted(tmp_path: Path, start_date: str) -> None:
    """Ours, and the correction to that reading. `parseStrict()` sets parse
    strictness; the resolver stays at its SMART default, which clamps to the
    previous valid day rather than rejecting. February 30th, February 29th in a
    non-leap year and April 31st are all valid start_dates to the jar, measured
    on JDK 17.0.19."""
    descriptor = td(trip_id="1.1", start_date=start_date, schedule_relationship=SCHEDULED)

    assert found(tmp_path, entity(trip_update={"trip": descriptor})) == []


@pytest.mark.parametrize("start_date", ["00000101", "20171301", "2017010", "20170101XYZ"])
def test_what_is_still_refused(tmp_path: Path, start_date: str) -> None:
    """Ours. Year 0 fails YEAR_OF_ERA, month 13 fails the field range, and both
    length cases fail the gate: the short one because the fields cannot be
    filled and the long one because `parse(text, ParsePosition)` would otherwise
    stop at the eighth character and call it a success."""
    descriptor = td(trip_id="1.1", start_date=start_date, schedule_relationship=SCHEDULED)

    assert found(tmp_path, entity(trip_update={"trip": descriptor})) == [
        f"trip_id 1.1 start_date is {start_date}"
    ]


def test_the_prefix_echoes_the_offending_string(tmp_path: Path) -> None:
    """Ours, read off `:316`, and the two `getVehicleAndTripIdText` shapes."""
    descriptor = td(trip_id="1.1", start_date="01-01-2017", schedule_relationship=SCHEDULED)
    named = entity(vehicle={"trip": descriptor, "vehicle": {"id": "V1"}})

    assert found(tmp_path, both(descriptor)) == [
        "trip_id 1.1 start_date is 01-01-2017",
        "vehicle_id  trip_id 1.1 start_date is 01-01-2017",
    ]
    assert found(tmp_path, named) == ["vehicle_id V1 trip_id 1.1 start_date is 01-01-2017"]
