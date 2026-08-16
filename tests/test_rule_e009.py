"""E009, against upstream's own `testE009`.

Every assertion marked "upstream" is transcribed from the real
`StopTimeUpdateValidatorTest.java` (`testE009`, `:407-651`), not from the
reference's summary of it. Upstream asserts counts and nothing else, so every
assertion about occurrence text is ours.

The feed is `bullrunner-gtfs.zip` trip `1`, whose 25 `stop_times.txt` rows visit
stop_id `222` at stop_sequence 1 and again at 25. Upstream's second feed is
`testagency.zip` trip `1.1`, stops A, B and C with no repeat, which is the
control: the same stop_time_updates report nothing there.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.upstream.e009 import check
from stufixtures import bullrunner, found, run, stu, trip_update

#: Upstream's nine stop_time_updates for trip `1`. Note the gaps: 1 to 6, then
#: 10, 12 and 25, which are the stop_sequences of the stop_ids it sends.
SEQUENCES = (1, 2, 3, 4, 5, 6, 10, 12, 25)
STOP_IDS = ("222", "230", "214", "204", "102", "101", "162", "154", "222")


def paired() -> list[dict[str, object]]:
    return [
        stu(sequence, stop_id, arrival={"delay": 60})
        for sequence, stop_id in zip(SEQUENCES, STOP_IDS, strict=True)
    ]


def stop_ids_only() -> list[dict[str, object]]:
    return [stu(stop_id=stop_id, arrival={"delay": 60}) for stop_id in STOP_IDS]


# --- upstream's testE009 ----------------------------------------------------


def test_stop_sequences_supplied_for_a_looping_trip_report_nothing(tmp_path):
    """Upstream, testE009: nine stop_time_updates carrying both fields,
    `expected.clear()`."""
    updates = trip_update(*paired(), trip_id="1")

    assert run(check, tmp_path, updates, tables=bullrunner()) == []


def test_stop_sequences_omitted_for_a_looping_trip_report_once(tmp_path):
    """Upstream, testE009: the same nine with stop_sequence cleared,
    `expected.put(E009, 1)`. Nine bare stop_time_updates, one occurrence."""
    updates = trip_update(*stop_ids_only(), trip_id="1")

    assert len(run(check, tmp_path, updates, tables=bullrunner())) == 1


def test_a_trip_with_no_repeated_stop_reports_nothing_however_it_is_addressed(tmp_path):
    """Upstream, testE009: `testagency.zip` trip `1.1` (stops A, B, C) with both
    fields, then with stop_sequence cleared, then with stop_id cleared. All
    three `expected.clear()`."""
    both = trip_update(stu(1, "A", arrival={"delay": 60}), stu(2, "B"), stu(3, "C"), trip_id="1.1")
    by_stop_id = trip_update(
        stu(stop_id="A", arrival={"delay": 60}), stu(stop_id="B"), stu(stop_id="C"), trip_id="1.1"
    )
    by_sequence = trip_update(stu(1, arrival={"delay": 60}), stu(2), stu(3), trip_id="1.1")

    assert run(check, tmp_path, both) == []
    assert run(check, tmp_path, by_stop_id) == []
    assert run(check, tmp_path, by_sequence) == []


# --- the occurrence text and the scope of the flag, which upstream never checks


def test_the_prefix_names_the_trip_and_every_repeat_visit(tmp_path):
    """Ours, read off `:102`. `getTripsWithMultiStops` collects a stop_id the
    *second* time it is seen, so a stop visited twice contributes one entry, and
    `List.toString()` renders it `[222]` rather than Python's `['222']`."""
    updates = trip_update(*stop_ids_only(), trip_id="1")

    assert found(run(check, tmp_path, updates, tables=bullrunner())) == [
        "trip_id 1 visits stop_id [222]"
    ]


def test_one_bare_stop_time_update_is_enough(tmp_path):
    """Ours. The condition is per stop_time_update, not per trip: a single one
    without a stop_sequence fires even when every other has one."""
    updates = trip_update(*paired()[:3], stu(stop_id="204", arrival={"delay": 60}), trip_id="1")

    assert len(run(check, tmp_path, updates, tables=bullrunner())) == 1


def test_two_entities_naming_one_trip_id_report_twice(tmp_path):
    """Ours, and the place a natural reading goes wrong: this looks like "at
    most one occurrence per trip" and is not. `foundE009error` is declared at `:94`, inside the
    entity loop, so it resets with every TripUpdate entity. A port that keyed
    the flag on trip_id would report once where the jar reports twice."""
    one = trip_update(*stop_ids_only(), trip_id="1")

    assert len(run(check, tmp_path, one, one, tables=bullrunner())) == 2


def test_a_trip_id_the_static_feed_does_not_have_reports_nothing(tmp_path):
    """Ours. `tripWithMultiStop.containsKey(tripId)` is the gate, and a trip
    absent from `stop_times.txt` is absent from that map too."""
    updates = trip_update(*stop_ids_only(), trip_id="NOT_A_TRIP")

    assert run(check, tmp_path, updates, tables=bullrunner()) == []


def test_a_trip_update_with_no_trip_id_reports_nothing(tmp_path):
    """Ours. `tripId != null` is the first half of the gate at `:99`, and the
    local stays null when the TripDescriptor has no trip_id."""
    assert run(check, tmp_path, trip_update(*stop_ids_only()), tables=bullrunner()) == []
