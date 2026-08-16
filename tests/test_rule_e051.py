"""E051, against upstream's own `testE051`.

Every assertion marked "upstream" is transcribed from the real
`StopTimeUpdateValidatorTest.java` (`testE051`, `:2420-2828`), not from the
reference's summary of it. Upstream asserts counts and nothing else, so every
assertion about occurrence text is ours.

The feed is `bullrunner-gtfs.zip` trip `1`, stop_sequences 1 through 25.
Upstream sends nine stop_time_updates carrying 1, 2, 3, 4, 5, 6, 10, 12 and 25,
and each case corrupts one of them.

What this rule's `break` does to the other eleven rules lives in
`test_shared_walk_stop_time_updates.py`, because it is a property of the walk
rather than of this rule's condition.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.upstream.e051 import check
from stufixtures import bullrunner, found, nine, run, stu, trip_update

#: Upstream's nine stop_sequences, and the stop_ids of those GTFS rows.
SEQUENCES = (1, 2, 3, 4, 5, 6, 10, 12, 25)
STOP_IDS = ("222", "230", "214", "204", "102", "101", "162", "154", "222")


def paired(*sequences: int) -> list[dict[str, object]]:
    return [
        stu(sequence, stop_id, arrival={"delay": 60})
        for sequence, stop_id in zip(sequences, STOP_IDS, strict=True)
    ]


def on_trip_one(tmp_path, updates):
    return run(check, tmp_path, trip_update(*updates, trip_id="1"), tables=bullrunner())


# --- upstream's testE051 ----------------------------------------------------


def test_every_stop_sequence_found_reports_nothing(tmp_path):
    """Upstream, testE051: stop_sequences only, all nine correct,
    `expected.clear()`."""
    assert on_trip_one(tmp_path, nine(*SEQUENCES)) == []


def test_a_wrong_last_stop_sequence_reports_once(tmp_path):
    """Upstream, testE051: 26 where 25 belongs, `expected.put(E051, 1)`."""
    assert len(on_trip_one(tmp_path, nine(*SEQUENCES[:8], 26))) == 1


def test_a_wrong_last_stop_sequence_with_stop_ids_reports_once(tmp_path):
    """Upstream, testE051: the same with stop_ids supplied too,
    `expected.put(E051, 1)`. The stop_ids change nothing: the stop-id branch is
    dead whenever a stop_sequence is present."""
    assert len(on_trip_one(tmp_path, paired(*SEQUENCES[:8], 26))) == 1


def test_a_wrong_stop_sequence_zero_at_the_start_reports_once(tmp_path):
    """Upstream, testE051: 0 where 1 belongs, `expected.put(E051, 1)`. The walk
    consumes all 25 GTFS rows looking for 0 and only then sets the flag, so the
    eight stop_time_updates after it are abandoned."""
    assert len(on_trip_one(tmp_path, paired(0, *SEQUENCES[1:]))) == 1


def test_a_wrong_stop_sequence_in_the_middle_reports_once(tmp_path):
    """Upstream, testE051: 250 where 6 belongs, with stop_ids,
    `expected.put(E051, 1)`."""
    assert len(on_trip_one(tmp_path, paired(*SEQUENCES[:5], 250, *SEQUENCES[6:]))) == 1


def test_a_wrong_stop_sequence_in_the_middle_without_stop_ids_reports_once(tmp_path):
    """Upstream, testE051: the same without stop_ids, `expected.put(E051, 1)`."""
    assert len(on_trip_one(tmp_path, nine(*SEQUENCES[:5], 250, *SEQUENCES[6:]))) == 1


# --- the occurrence text and the reach of the rule, which upstream skips ----


def test_the_prefix_names_the_trip_and_the_offending_stop_sequence(tmp_path):
    """Ours, read off `:175`. The number is the stop_time_update's own, even
    though the flag was set 19 GTFS rows later."""
    assert found(on_trip_one(tmp_path, paired(*SEQUENCES[:5], 250, *SEQUENCES[6:]))) == [
        "GTFS-rt trip_id 1 contains stop_sequence 250"
    ]


def test_only_the_first_offender_of_a_trip_is_reported(tmp_path):
    """Ours, and the `break`. Two bad stop_sequences give one occurrence, for
    the first, because the second is never reached."""
    assert found(on_trip_one(tmp_path, nine(250, 251))) == [
        "GTFS-rt trip_id 1 contains stop_sequence 250"
    ]


def test_a_stop_sequence_after_the_walk_ran_out_of_rows_reports_nothing(tmp_path):
    """Ours, and the trap in the flag's placement. `unknownRtStopSequence` is set
    at `:148-151` only when the index *reaches* the end during this
    stop_time_update's `while` loop. Once the index is already there the loop
    body never runs, so a wrong stop_sequence after a matched 25 is silently
    accepted. Upstream's own behaviour; do not tidy it."""
    assert on_trip_one(tmp_path, nine(25, 250)) == []


def test_a_stop_time_update_with_no_stop_sequence_reports_nothing(tmp_path):
    """Ours. `stopTimeUpdate.hasStopSequence()` is the first half of `:148`, so
    a feed addressing stops by stop_id alone can never trip this rule."""
    updates = [stu(stop_id="NOT_A_STOP", arrival={"delay": 60})]

    assert on_trip_one(tmp_path, updates) == []


def test_a_trip_absent_from_stop_times_reports_nothing(tmp_path):
    """Ours. `gtfsStopTimes` stays null (`:80-86`), so there is nothing to run
    out of and the rule cannot fire however wrong the stop_sequence is."""
    updates = trip_update(stu(250, arrival={"delay": 60}), trip_id="NOT_A_TRIP")

    assert run(check, tmp_path, updates, tables=bullrunner()) == []


def test_each_trip_gets_its_own_verdict(tmp_path):
    """Ours. The flag is declared per entity at `:97`, so a second TripUpdate
    naming the same trip_id starts from GTFS row 0 again and reports its own."""
    one = trip_update(stu(250, arrival={"delay": 60}), trip_id="1")

    assert len(run(check, tmp_path, one, one, tables=bullrunner())) == 2
