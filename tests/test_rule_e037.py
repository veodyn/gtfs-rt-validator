"""E037, against upstream's own `testE037`.

Every assertion marked "upstream" is transcribed from the real
`StopTimeUpdateValidatorTest.java` (`testE037`, `:772-884`), not from the
reference's summary of it. Upstream asserts counts and nothing else, so every
assertion about occurrence text is ours.

Upstream's fixture names trip `1234`, which `testagency.zip` does not have, so
`gtfsStopTimes` is null throughout and nothing here depends on the static feed.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.upstream.e037 import check
from stufixtures import found, run, stu, trip_update

TRIP = "1234"


def delayed(stop_sequence: int | None = None, stop_id: str | None = None) -> dict[str, object]:
    return stu(stop_sequence, stop_id, arrival={"delay": 60})


# --- upstream's testE037 ----------------------------------------------------


def test_two_different_stop_ids_report_nothing(tmp_path):
    """Upstream, testE037: stop_ids 1000, 2000, `expected.clear()`."""
    updates = trip_update(delayed(stop_id="1000"), delayed(stop_id="2000"), trip_id=TRIP)

    assert run(check, tmp_path, updates) == []


def test_two_different_stop_ids_with_stop_sequences_report_nothing(tmp_path):
    """Upstream, testE037: the same pair carrying stop_sequences 1 and 5."""
    updates = trip_update(delayed(1, "1000"), delayed(5, "2000"), trip_id=TRIP)

    assert run(check, tmp_path, updates) == []


def test_a_repeated_stop_id_with_no_stop_sequence_reports_once(tmp_path):
    """Upstream, testE037: 1000, 2000, 2000 where the last carries no
    stop_sequence, `expected.put(E037, 1)`."""
    updates = trip_update(
        delayed(1, "1000"), delayed(5, "2000"), delayed(stop_id="2000"), trip_id=TRIP
    )

    assert len(run(check, tmp_path, updates)) == 1


def test_a_repeated_stop_id_with_a_stop_sequence_reports_once(tmp_path):
    """Upstream, testE037: the same three with stop_sequence 10 on the last."""
    updates = trip_update(delayed(1, "1000"), delayed(5, "2000"), delayed(10, "2000"), trip_id=TRIP)

    assert len(run(check, tmp_path, updates)) == 1


# --- the occurrence text and the guard, which upstream never checks ---------


def test_the_prefix_names_the_trip_and_the_repeated_stop_id(tmp_path):
    """Ours, read off `:271-275`. No `at stop_sequence` clause when this
    stop_time_update has none, which is upstream's `StringBuilder` branch."""
    updates = trip_update(delayed(stop_id="2000"), delayed(stop_id="2000"), trip_id=TRIP)

    assert found(run(check, tmp_path, updates)) == ["trip_id 1234 has repeating stop_id 2000"]


def test_the_prefix_gains_a_stop_sequence_clause_when_this_update_has_one(tmp_path):
    """Ours, read off `:276-279`. The clause reports *this* stop_time_update's
    stop_sequence, not the previous one's, which is the pair that makes the two
    distinguishable."""
    updates = trip_update(delayed(5, "2000"), delayed(10, "2000"), trip_id=TRIP)

    assert found(run(check, tmp_path, updates)) == [
        "trip_id 1234 has repeating stop_id 2000 at stop_sequence 10"
    ]


def test_three_identical_stop_ids_in_a_row_report_twice(tmp_path):
    """Ours. The check runs per adjacent pair, so a run of three is two pairs."""
    one = delayed(stop_id="2000")
    updates = trip_update(one, one, one, trip_id=TRIP)

    assert len(run(check, tmp_path, updates)) == 2


def test_a_repeat_that_is_not_adjacent_reports_nothing(tmp_path):
    """Ours. Only the immediately previous stop_time_update is remembered, which
    is why a route with a genuine loop reports E009 rather than this."""
    updates = trip_update(
        delayed(stop_id="222"), delayed(stop_id="230"), delayed(stop_id="222"), trip_id=TRIP
    )

    assert run(check, tmp_path, updates) == []


def test_two_stop_time_updates_with_no_stop_id_report_nothing(tmp_path):
    """Ours, and the `!previousStopId.isEmpty()` guard at `:269`. The unguarded
    assignment at `:112` stored the empty string for the first one, and without
    that guard the second one would match it."""
    updates = trip_update(delayed(1), delayed(2), trip_id=TRIP)

    assert run(check, tmp_path, updates) == []


def test_an_explicit_empty_stop_id_is_indistinguishable_from_an_absent_one(tmp_path):
    """Ours. `isEmpty()` cannot tell the two apart, so a feed that sets stop_id
    to `""` twice reports nothing. Upstream's behaviour, not a simplification."""
    updates = trip_update(delayed(1, ""), delayed(2, ""), trip_id=TRIP)

    assert run(check, tmp_path, updates) == []


def test_the_first_stop_time_update_has_nothing_to_repeat(tmp_path):
    """Ours. `previousRtStopId` starts null (`:93`) and the call at `:108` is
    guarded on it, so a single stop_time_update can never report."""
    assert run(check, tmp_path, trip_update(delayed(stop_id="2000"), trip_id=TRIP)) == []
