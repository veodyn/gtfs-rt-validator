"""E020, against upstream's own `testE020`.

Upstream asserts counts only; the prefixes are ours, read off
`TripDescriptorValidator.java:276`. Upstream runs this one against
`bullRunnerGtfs` with trip_id `1`, and `tripfixtures.feed_tables` carries that
trip on route `A` for the same reason.

The grammar itself is pinned in `tests/test_shared_timeformats.py`; what is
pinned here is that this rule is the caller of it, that the `hasStartTime()`
gate is what keeps a feed with no start_time silent, and that the offending
string is echoed into the occurrence verbatim.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.rules.upstream.e020 import check
from rulefixtures import entity, prefixes
from tripfixtures import DUPLICATED, SCHEDULED, both, run, td


def found(tmp_path: Path, *entities) -> list[str]:
    return prefixes(run(check, tmp_path, *entities))


def test_no_start_time_at_all_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE020's first stage. The gate is `hasStartTime()` at `:118`
    and `:167`, so the empty-string default is never handed to the format
    test."""
    assert found(tmp_path, both(td(trip_id="1", schedule_relationship=SCHEDULED))) == []


@pytest.mark.parametrize("start_time", ["00:20:00", "26:59:59", "5:15:35"])
def test_a_valid_start_time_reports_nothing(tmp_path: Path, start_time: str) -> None:
    """Upstream, testE020: `00:20:00`, `26:59:59` and `5:15:35` all clear.
    The last is the H:MM:SS case the final upstream change to `validation/`
    added, and hours past 23 are legal because service continues into the next
    service day."""
    descriptor = td(trip_id="1", start_time=start_time, schedule_relationship=SCHEDULED)

    assert found(tmp_path, both(descriptor)) == []


@pytest.mark.parametrize("start_time", ["005:15:35", "00:60:60", "30:00:00"])
def test_an_invalid_start_time_reports_once_per_carrier(tmp_path: Path, start_time: str) -> None:
    """Upstream, testE020: `005:15:35`, `00:60:60` and `30:00:00`, each
    `expected.put(E020, 2)`."""
    descriptor = td(trip_id="1", start_time=start_time, schedule_relationship=SCHEDULED)

    assert len(found(tmp_path, both(descriptor))) == 2


def test_the_length_gate_admits_h_mm_ss_and_refuses_hh_m_ss(tmp_path: Path) -> None:
    """Ours. Upstream tests the first half and not the second, and the two
    together are what the length gate does: seven or eight characters, so a
    single-digit hour is legal and a single-digit minute is not."""
    short_hour = td(trip_id="1", start_time="5:15:35", schedule_relationship=SCHEDULED)
    short_minute = td(trip_id="1", start_time="05:5:35", schedule_relationship=SCHEDULED)

    assert found(tmp_path, entity(trip_update={"trip": short_hour})) == []
    assert found(tmp_path, entity(trip_update={"trip": short_minute})) == [
        "trip_id 1 start_time is 05:5:35"
    ]


def test_the_prefix_echoes_the_offending_string(tmp_path: Path) -> None:
    """Ours, read off `:276`, and the two `getVehicleAndTripIdText` shapes."""
    descriptor = td(trip_id="1", start_time="30:00:00", schedule_relationship=SCHEDULED)
    named = entity(vehicle={"trip": descriptor, "vehicle": {"id": "V1"}})

    assert found(tmp_path, both(descriptor)) == [
        "trip_id 1 start_time is 30:00:00",
        "vehicle_id  trip_id 1 start_time is 30:00:00",
    ]
    assert found(tmp_path, named) == ["vehicle_id V1 trip_id 1 start_time is 30:00:00"]


def test_a_post_2015_schedule_relationship_changes_nothing_here(tmp_path: Path) -> None:
    """Ours, and a claim worth pinning because an earlier draft named E020 as
    enum-sensitive. It is not: the gate reads `hasStartTime()`
    alone and the body reads `start_time` alone, so the same bad start_time
    reports the same way whatever the schedule_relationship is."""
    bad = "30:00:00"
    duplicated = td(trip_id="1", start_time=bad, schedule_relationship=DUPLICATED)
    scheduled = td(trip_id="1", start_time=bad, schedule_relationship=SCHEDULED)

    assert found(tmp_path, both(duplicated)) == found(tmp_path, both(scheduled))
