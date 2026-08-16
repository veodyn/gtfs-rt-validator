"""E023, against upstream's own `testE023`.

Upstream asserts counts only; the prefixes are ours, read off
`TripDescriptorValidator.java:300`.

Upstream's feed is `testagency.zip`, whose trip `1.2` has arrival_times
`00:20:00` at stop_sequence 1 and `00:30:00` at 2. `tripfixtures.feed_tables`
carries that trip with those two rows, plus two the upstream test has no
counterpart for: `1.3`, whose first stop has no arrival_time at all, and the
frequency-based `f0` and `f1`.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.upstream.e023 import check
from rulefixtures import entity, prefixes
from tripfixtures import SCHEDULED, both, run, td

TRIP_UPDATE_TEXT = (
    "GTFS-rt trip_id 1.2 start_time is 00:30:00 and GTFS initial arrival_time is 00:20:00"
)
VEHICLE_TEXT = (
    "GTFS-rt vehicle_id  trip_id 1.2 start_time is 00:30:00 "
    "and GTFS initial arrival_time is 00:20:00"
)
NAMED_VEHICLE_TEXT = (
    "GTFS-rt vehicle_id V1 trip_id 1.2 start_time is 00:30:00 "
    "and GTFS initial arrival_time is 00:20:00"
)


def found(tmp_path: Path, *entities) -> list[str]:
    return prefixes(run(check, tmp_path, *entities))


def trip(trip_id: str, start_time: str | None = None) -> dict[str, object]:
    fields: dict[str, object] = {"trip_id": trip_id, "schedule_relationship": SCHEDULED}
    if start_time is not None:
        fields["start_time"] = start_time
    return td(**fields)


def test_no_start_time_at_all_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE023's first stage. The call is gated on `hasStartTime()`
    at `:112` and `:160`, inside the arm that already knows the trip exists."""
    assert found(tmp_path, both(trip("1.2"))) == []


def test_a_start_time_that_matches_the_first_arrival_time_reports_nothing(
    tmp_path: Path,
) -> None:
    """Upstream, testE023: start_time `00:20:00` on trip `1.2`, `expected.clear()`."""
    assert found(tmp_path, both(trip("1.2", "00:20:00"))) == []


def test_a_start_time_that_does_not_match_reports_once_per_carrier(tmp_path: Path) -> None:
    """Upstream, testE023: start_time `00:30:00`, `expected.put(E023, 2)`."""
    assert len(found(tmp_path, both(trip("1.2", "00:30:00")))) == 2


def test_a_trip_id_that_is_in_no_gtfs_row_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE023's last stage: trip_id `100000000` with a valid
    start_time gives 0 E023 and 2 E003. The early return on an empty stop_times
    list is the fix for issue #217, and reaching it needs no null check."""
    assert found(tmp_path, both(trip("100000000", "00:20:00"))) == []


# --- ours ----------------------------------------------------------------


def test_the_prefix_names_both_times(tmp_path: Path) -> None:
    """Ours, read off `:300`, and the two `getVehicleAndTripIdText` shapes."""
    named = entity(vehicle={"trip": trip("1.2", "00:30:00"), "vehicle": {"id": "V1"}})

    assert found(tmp_path, both(trip("1.2", "00:30:00"))) == [
        TRIP_UPDATE_TEXT,
        VEHICLE_TEXT,
    ]
    assert found(tmp_path, named) == [NAMED_VEHICLE_TEXT]


def test_only_the_first_stop_time_is_read(tmp_path: Path) -> None:
    """Ours. `00:30:00` is trip `1.2`'s *second* arrival_time, and it still
    reports, because `stopTimes.get(0)` is the only row this rule looks at. It
    is why E023 must not be folded into the stateful stop_time_update walk."""
    assert len(found(tmp_path, entity(trip_update={"trip": trip("1.2", "00:30:00")}))) == 1


def test_a_first_stop_with_no_arrival_time_prints_the_missing_value_sentinel(
    tmp_path: Path,
) -> None:
    """Ours, and the trap. onebusaway's `StopTime.getArrivalTime()` is a
    primitive `int` whose unset value is -999, and
    `secondsAfterMidnightToClock(-999)` renders `00:-16:-39` under Java's
    truncating division and sign-of-dividend remainder. The comparison then
    fails for every real start_time and that string reaches the report."""
    found_prefixes = found(tmp_path, entity(trip_update={"trip": trip("1.3", "00:40:00")}))

    assert found_prefixes == [
        "GTFS-rt trip_id 1.3 start_time is 00:40:00 and GTFS initial arrival_time is 00:-16:-39"
    ]


def test_a_frequency_based_trip_of_either_kind_is_exempt(tmp_path: Path) -> None:
    """Ours. `exactTimesZeroTripIds` and `exactTimesOneTrips` are both consulted
    at `:290`, and `f0` and `f1` share `1.2`'s first arrival_time, so without the
    exemption both would report."""
    assert found(tmp_path, entity(trip_update={"trip": trip("f0", "00:30:00")})) == []
    assert found(tmp_path, entity(trip_update={"trip": trip("f1", "00:30:00")})) == []
