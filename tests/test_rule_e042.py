"""E042, against upstream's own `testE42`.

Every assertion marked "upstream" is transcribed from the real
`StopTimeUpdateValidatorTest.java` (`testE42`, `:1030-1117`), not from the
reference's summary of it. Upstream asserts counts and nothing else, so every
assertion about occurrence text is ours.

Upstream's fixture names trip `1` against `testagency.zip`, which does not have
it, and flips the *trip's* schedule_relationship to CANCELED partway through
without that mattering to this rule: what E042 reads is the **stop_time_update**
enum, which is a different one.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.upstream.e042 import check
from stufixtures import found, run, stu, trip_update

#: `TripUpdate.StopTimeUpdate.ScheduleRelationship`, not the trip's.
SCHEDULED = 0
SKIPPED = 1
NO_DATA = 2

TRIP = "1"
STOP = "1.1"


# --- upstream's testE42 -----------------------------------------------------


def test_a_scheduled_stop_time_update_with_a_departure_reports_nothing(tmp_path):
    """Upstream, testE42: SCHEDULED with a departure delay, `expected.clear()`."""
    updates = trip_update(
        stu(stop_id=STOP, departure={"delay": 60}, schedule_relationship=SCHEDULED), trip_id=TRIP
    )

    assert run(check, tmp_path, updates) == []


def test_a_scheduled_stop_time_update_with_an_arrival_reports_nothing(tmp_path):
    """Upstream, testE42: SCHEDULED with an arrival delay, `expected.clear()`."""
    updates = trip_update(
        stu(stop_id=STOP, arrival={"delay": 60}, schedule_relationship=SCHEDULED), trip_id=TRIP
    )

    assert run(check, tmp_path, updates) == []


def test_a_no_data_stop_time_update_with_a_departure_reports_once(tmp_path):
    """Upstream, testE42: NO_DATA with a departure, `expected.put(E042, 1)`."""
    updates = trip_update(
        stu(stop_id=STOP, departure={"delay": 60}, schedule_relationship=NO_DATA), trip_id=TRIP
    )

    assert len(run(check, tmp_path, updates)) == 1


def test_a_no_data_stop_time_update_with_an_arrival_reports_once(tmp_path):
    """Upstream, testE42: NO_DATA with an arrival, `expected.put(E042, 1)`."""
    updates = trip_update(
        stu(stop_id=STOP, arrival={"delay": 60}, schedule_relationship=NO_DATA), trip_id=TRIP
    )

    assert len(run(check, tmp_path, updates)) == 1


# --- the occurrence text and the two tests, which upstream never checks -----


def test_the_prefix_names_the_trip_the_stop_time_update_and_which_half(tmp_path):
    """Ours, read off `:328-334`. `getStopTimeUpdateId` prefers stop_sequence,
    so a stop_time_update carrying both is named by its stop_sequence."""
    updates = trip_update(
        stu(4, STOP, arrival={"delay": 60}, schedule_relationship=NO_DATA), trip_id=TRIP
    )

    assert found(run(check, tmp_path, updates)) == ["trip_id 1 stop_sequence 4 has arrival"]


def test_a_stop_time_update_with_only_a_stop_id_is_named_by_it(tmp_path):
    """Ours, the other arm of `getStopTimeUpdateId`."""
    updates = trip_update(
        stu(stop_id=STOP, arrival={"delay": 60}, schedule_relationship=NO_DATA), trip_id=TRIP
    )

    assert found(run(check, tmp_path, updates)) == ["trip_id 1 stop_id 1.1 has arrival"]


def test_both_halves_report_independently_and_arrival_comes_first(tmp_path):
    """Ours. `:330` and `:333` are two `if`s, not an either-or, so one NO_DATA
    stop_time_update carrying both gives two occurrences."""
    updates = trip_update(
        stu(4, arrival={"delay": 60}, departure={"delay": 60}, schedule_relationship=NO_DATA),
        trip_id=TRIP,
    )

    assert found(run(check, tmp_path, updates)) == [
        "trip_id 1 stop_sequence 4 has arrival",
        "trip_id 1 stop_sequence 4 has departure",
    ]


def test_a_no_data_stop_time_update_with_neither_reports_nothing(tmp_path):
    """Ours. Both tests are on presence, so a bare NO_DATA update is exactly what
    the rule wants and reports here (E043 exempts it too)."""
    updates = trip_update(stu(4, schedule_relationship=NO_DATA), trip_id=TRIP)

    assert run(check, tmp_path, updates) == []


def test_a_skipped_stop_time_update_with_an_arrival_reports_nothing(tmp_path):
    """Ours. `:327` compares against NO_DATA alone; SKIPPED is E043's and E044's
    business, not this rule's."""
    updates = trip_update(
        stu(4, arrival={"delay": 60}, schedule_relationship=SKIPPED), trip_id=TRIP
    )

    assert run(check, tmp_path, updates) == []


def test_an_absent_schedule_relationship_reports_nothing(tmp_path):
    """Ours, and where the 2015 schema shows through. `hasScheduleRelationship()`
    gates the whole check, and a post-2015 value reads as absent under compat,
    so this rule simply cannot fire for one."""
    updates = trip_update(stu(4, arrival={"delay": 60}), trip_id=TRIP)

    assert run(check, tmp_path, updates) == []


def test_a_stop_time_update_with_neither_field_renders_a_trailing_space(tmp_path):
    """Ours. `getStopTimeUpdateId` falls back to an unguarded `getStopId()`
    (`GtfsUtils.java:240`), so an update with neither gives `"stop_id "`. E040
    reports that update too, which is what makes this text reachable."""
    updates = trip_update(stu(arrival={"delay": 60}, schedule_relationship=NO_DATA), trip_id=TRIP)

    assert found(run(check, tmp_path, updates)) == ["trip_id 1 stop_id  has arrival"]
