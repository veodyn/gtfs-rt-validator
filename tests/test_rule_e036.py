"""E036, against upstream's own `testE036`.

Every assertion marked "upstream" is transcribed from the real
`StopTimeUpdateValidatorTest.java` (`testE036`, `:657-771`), not from the
reference's summary of it. Upstream asserts counts and nothing else, so every
assertion about occurrence text is ours.

Upstream's fixture names trip `1234`, which `testagency.zip` does not have, so
`gtfsStopTimes` is null throughout and nothing here depends on the static feed.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.upstream.e036 import check
from stufixtures import found, nine, run, stu, trip_update

TRIP = "1234"


def delayed(stop_sequence: int | None = None, stop_id: str | None = None) -> dict[str, object]:
    return stu(stop_sequence, stop_id, arrival={"delay": 60})


# --- upstream's testE036 ----------------------------------------------------


def test_two_different_stop_sequences_report_nothing(tmp_path):
    """Upstream, testE036: stop_sequences 1, 5, `expected.clear()`."""
    assert run(check, tmp_path, trip_update(*nine(1, 5), trip_id=TRIP)) == []


def test_two_different_stop_sequences_with_stop_ids_report_nothing(tmp_path):
    """Upstream, testE036: the same pair carrying stop_ids 1000 and 2000."""
    updates = trip_update(delayed(1, "1000"), delayed(5, "2000"), trip_id=TRIP)

    assert run(check, tmp_path, updates) == []


def test_a_repeated_stop_sequence_with_no_stop_id_reports_once(tmp_path):
    """Upstream, testE036: 1, 5, 5 where the last carries no stop_id,
    `expected.put(E036, 1)` alongside the E002 that file carries."""
    updates = trip_update(delayed(1, "1000"), delayed(5, "2000"), delayed(5), trip_id=TRIP)

    assert len(run(check, tmp_path, updates)) == 1


def test_a_repeated_stop_sequence_with_a_stop_id_reports_once(tmp_path):
    """Upstream, testE036: 1, 5, 5 where the last carries stop_id 3000. The
    stop_id is irrelevant to this rule, which is the point of the pair."""
    updates = trip_update(delayed(1, "1000"), delayed(5, "2000"), delayed(5, "3000"), trip_id=TRIP)

    assert len(run(check, tmp_path, updates)) == 1


# --- the occurrence text and the comparison, which upstream never checks ----


def test_the_prefix_names_the_trip_and_the_repeated_stop_sequence(tmp_path):
    """Ours, read off `:255`. The number printed is `previousStopSequence`,
    which is equal to this one by the time it is printed."""
    updates = trip_update(delayed(5), delayed(5), trip_id=TRIP)

    assert found(run(check, tmp_path, updates)) == ["trip_id 1234 has repeating stop_sequence 5"]


def test_three_identical_stop_sequences_in_a_row_report_twice(tmp_path):
    """Ours. The check runs per adjacent pair, so a run of three is two pairs."""
    updates = trip_update(delayed(5), delayed(5), delayed(5), trip_id=TRIP)

    assert len(run(check, tmp_path, updates)) == 2


def test_a_repeat_that_is_not_adjacent_reports_nothing(tmp_path):
    """Ours. Only the immediately previous stop_time_update is remembered, so
    1, 5, 1 is two changes and no repeat, even though it is unsorted."""
    updates = trip_update(delayed(1), delayed(5), delayed(1), trip_id=TRIP)

    assert run(check, tmp_path, updates) == []


def test_a_stop_sequence_above_the_integer_cache_still_compares_equal(tmp_path):
    """Ours, and the reason the comparison is numeric rather than by identity.
    `previousStopSequence` is an `Integer` and `getStopSequence()` an `int`, so
    Java unboxes; a port that compared identity would pass at 5 and fail here,
    because 1000 is outside `Integer.valueOf`'s cache."""
    updates = trip_update(delayed(1000), delayed(1000), trip_id=TRIP)

    assert found(run(check, tmp_path, updates)) == ["trip_id 1234 has repeating stop_sequence 1000"]


def test_an_absent_stop_sequence_followed_by_zero_reports(tmp_path):
    """Ours, and the unguarded getter at `:111`. The first stop_time_update has
    no stop_sequence, which stores 0, and an explicit 0 next to it repeats it.
    A port that carried `None` forward instead would report nothing."""
    updates = trip_update(delayed(stop_id="A"), delayed(0), trip_id=TRIP)

    assert found(run(check, tmp_path, updates)) == ["trip_id 1234 has repeating stop_sequence 0"]


def test_two_stop_time_updates_with_no_stop_sequence_report_nothing(tmp_path):
    """Ours. `stopTimeUpdate.hasStopSequence()` guards the second operand, so
    the 0 that was stored is never compared against another absent field."""
    updates = trip_update(delayed(stop_id="A"), delayed(stop_id="B"), trip_id=TRIP)

    assert run(check, tmp_path, updates) == []


def test_the_first_stop_time_update_has_nothing_to_repeat(tmp_path):
    """Ours. `previousRtStopSequence` starts null (`:92`) and the call at `:105`
    is guarded on it, so a single stop_time_update can never report."""
    assert run(check, tmp_path, trip_update(delayed(1), trip_id=TRIP)) == []
