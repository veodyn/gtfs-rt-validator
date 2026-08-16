"""E043, against upstream's own `testE43`.

Every assertion marked "upstream" is transcribed from the real
`StopTimeUpdateValidatorTest.java` (`testE43`, `:1118-1220`), not from the
reference's summary of it. Upstream asserts counts and nothing else, so every
assertion about occurrence text is ours.

Upstream's fixture names trip `1` against `testagency.zip`, which does not have
it, so the static half of the walk never engages.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.upstream.e043 import check
from stufixtures import found, run, stu, trip_update

SCHEDULED = 0
SKIPPED = 1
NO_DATA = 2

TRIP = "1"
STOP = "1.1"


# --- upstream's testE43 -----------------------------------------------------


def test_neither_arrival_nor_departure_reports_once(tmp_path):
    """Upstream, testE43: SCHEDULED with neither, `expected.put(E043, 1)`."""
    updates = trip_update(stu(stop_id=STOP, schedule_relationship=SCHEDULED), trip_id=TRIP)

    assert len(run(check, tmp_path, updates)) == 1


def test_a_skipped_stop_time_update_is_exempt(tmp_path):
    """Upstream, testE43: SKIPPED with neither, `expected.clear()`."""
    updates = trip_update(stu(stop_id=STOP, schedule_relationship=SKIPPED), trip_id=TRIP)

    assert run(check, tmp_path, updates) == []


def test_a_no_data_stop_time_update_is_exempt(tmp_path):
    """Upstream, testE43: NO_DATA with neither, `expected.clear()`."""
    updates = trip_update(stu(stop_id=STOP, schedule_relationship=NO_DATA), trip_id=TRIP)

    assert run(check, tmp_path, updates) == []


def test_an_arrival_is_enough(tmp_path):
    """Upstream, testE43: SCHEDULED with an arrival delay, `expected.clear()`."""
    updates = trip_update(
        stu(stop_id=STOP, arrival={"delay": 60}, schedule_relationship=SCHEDULED), trip_id=TRIP
    )

    assert run(check, tmp_path, updates) == []


def test_a_departure_is_enough(tmp_path):
    """Upstream, testE43: SCHEDULED with a departure delay, `expected.clear()`."""
    updates = trip_update(
        stu(stop_id=STOP, departure={"delay": 60}, schedule_relationship=SCHEDULED), trip_id=TRIP
    )

    assert run(check, tmp_path, updates) == []


# --- the occurrence text and the presence test, which upstream never checks --


def test_the_prefix_names_the_trip_and_the_stop_time_update(tmp_path):
    """Ours, read off `:355`. No suffix of its own beyond the manifest's, unlike
    E042's `has arrival` and E044's ` arrival`."""
    updates = trip_update(stu(4, STOP, schedule_relationship=SCHEDULED), trip_id=TRIP)

    assert found(run(check, tmp_path, updates)) == ["trip_id 1 stop_sequence 4"]


def test_an_empty_arrival_still_counts_as_present(tmp_path):
    """Ours, and the seam with E044. `hasArrival()` is presence, not content, so
    an arrival carrying neither delay nor time satisfies this rule and is
    reported by E044 instead."""
    updates = trip_update(stu(4, arrival={}, schedule_relationship=SCHEDULED), trip_id=TRIP)

    assert run(check, tmp_path, updates) == []


def test_an_absent_schedule_relationship_is_not_exempt(tmp_path):
    """Ours. The exemption at `:349` needs `hasScheduleRelationship()`, so a
    stop_time_update that names no relationship at all is reported, and so is
    one carrying a post-2015 value that the 2015 schema cannot see."""
    assert len(run(check, tmp_path, trip_update(stu(4), trip_id=TRIP))) == 1


def test_each_silent_stop_time_update_reports_once(tmp_path):
    """Ours. The check is per stop_time_update with no de-duplication."""
    assert len(run(check, tmp_path, trip_update(stu(4), stu(5), trip_id=TRIP))) == 2
