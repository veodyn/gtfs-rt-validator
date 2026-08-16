"""E044, against upstream's own `testE44`.

Every assertion marked "upstream" is transcribed from the real
`StopTimeUpdateValidatorTest.java` (`testE44`, `:1221-1391`), not from the
reference's summary of it. Upstream asserts counts and nothing else, so every
assertion about occurrence text is ours.

Upstream's fixture names trip `1` against `testagency.zip`, which does not have
it, and uses `TimestampUtils.MIN_POSIX_TIME` for the time cases; the value is
irrelevant to the rule, which only asks whether the field is there.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.upstream.e044 import check
from stufixtures import found, run, stu, trip_update

SCHEDULED = 0
SKIPPED = 1
NO_DATA = 2

#: `TimestampUtils.MIN_POSIX_TIME`, upstream's stand-in for a real time.
MIN_POSIX_TIME = 1104537600

TRIP = "1"
STOP = "1.1"


def one(**fields: object) -> dict[str, object]:
    return trip_update(stu(stop_id=STOP, schedule_relationship=SCHEDULED, **fields), trip_id=TRIP)


# --- upstream's testE44 -----------------------------------------------------


def test_an_arrival_with_a_delay_reports_nothing(tmp_path):
    """Upstream, testE44: `expected.clear()`."""
    assert run(check, tmp_path, one(arrival={"delay": 60})) == []


def test_an_arrival_with_a_time_reports_nothing(tmp_path):
    """Upstream, testE44: `expected.clear()`."""
    assert run(check, tmp_path, one(arrival={"time": MIN_POSIX_TIME})) == []


def test_a_departure_with_a_delay_reports_nothing(tmp_path):
    """Upstream, testE44: `expected.clear()`."""
    assert run(check, tmp_path, one(departure={"delay": 60})) == []


def test_a_departure_with_a_time_reports_nothing(tmp_path):
    """Upstream, testE44: `expected.clear()`."""
    assert run(check, tmp_path, one(departure={"time": MIN_POSIX_TIME})) == []


def test_an_arrival_with_neither_reports_once(tmp_path):
    """Upstream, testE44: `StopTimeEvent.newBuilder().build()`,
    `expected.put(E044, 1)`."""
    assert len(run(check, tmp_path, one(arrival={}))) == 1


def test_a_departure_with_neither_reports_once(tmp_path):
    """Upstream, testE44: `expected.put(E044, 1)`."""
    assert len(run(check, tmp_path, one(departure={}))) == 1


def test_an_empty_arrival_on_a_skipped_stop_time_update_reports_nothing(tmp_path):
    """Upstream, testE44: SKIPPED, `expected.clear()`. Upstream issue #243."""
    updates = trip_update(
        stu(stop_id=STOP, arrival={}, schedule_relationship=SKIPPED), trip_id=TRIP
    )

    assert run(check, tmp_path, updates) == []


def test_an_empty_departure_on_a_skipped_stop_time_update_reports_nothing(tmp_path):
    """Upstream, testE44: SKIPPED, `expected.clear()`."""
    updates = trip_update(
        stu(stop_id=STOP, departure={}, schedule_relationship=SKIPPED), trip_id=TRIP
    )

    assert run(check, tmp_path, updates) == []


# --- the occurrence text and the NO_DATA asymmetry, which upstream skips ----


def test_the_prefix_names_the_trip_the_stop_time_update_and_which_half(tmp_path):
    """Ours, read off `:373-379`. A space and the field name, where E042 writes
    ` has arrival` for the same position."""
    updates = trip_update(stu(4, arrival={}, schedule_relationship=SCHEDULED), trip_id=TRIP)

    assert found(run(check, tmp_path, updates)) == ["trip_id 1 stop_sequence 4 arrival"]


def test_both_halves_report_independently_and_arrival_comes_first(tmp_path):
    """Ours. `:374` and `:377` are two `if`s, so one stop_time_update carrying
    two empty events gives two occurrences."""
    updates = trip_update(
        stu(4, arrival={}, departure={}, schedule_relationship=SCHEDULED), trip_id=TRIP
    )

    assert found(run(check, tmp_path, updates)) == [
        "trip_id 1 stop_sequence 4 arrival",
        "trip_id 1 stop_sequence 4 departure",
    ]


def test_no_data_is_not_exempt_here_unlike_e043(tmp_path):
    """Ours, and the asymmetry worth pinning. `:369` returns early for SKIPPED
    alone, so an empty arrival on a NO_DATA stop_time_update is reported here
    even though E043 exempts the same relationship."""
    updates = trip_update(stu(4, arrival={}, schedule_relationship=NO_DATA), trip_id=TRIP)

    assert found(run(check, tmp_path, updates)) == ["trip_id 1 stop_sequence 4 arrival"]


def test_a_delay_of_zero_still_counts_as_present(tmp_path):
    """Ours. `hasDelay()` is presence, and 0 is a perfectly good delay, so a
    port reading the value rather than the presence would report here."""
    assert run(check, tmp_path, one(arrival={"delay": 0})) == []


def test_an_absent_arrival_reports_nothing(tmp_path):
    """Ours. Only a *present* arrival is examined; a stop_time_update with none
    is E043's business."""
    assert run(check, tmp_path, one(departure={"delay": 60})) == []
