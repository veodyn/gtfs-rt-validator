"""E045, against upstream's own `testE45`.

Every assertion marked "upstream" is transcribed from the real
`StopTimeUpdateValidatorTest.java` (`testE45`, `:1392-2040`), not from the
reference's summary of it. Upstream asserts counts and nothing else, so every
assertion about occurrence text is ours.

The feed is `bullrunner-gtfs.zip` trip `1`. Upstream's nine stop_time_updates
carry stop_sequences 1, 2, 3, 4, 5, 6, 10, 12 and 25 paired with the stop_ids
those rows hold, and each case changes one or two pairings.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.upstream.e045 import check
from stufixtures import bullrunner, found, run, stu, trip_update

#: Upstream's nine correct pairings, in order.
CORRECT = (
    (1, "222"),
    (2, "230"),
    (3, "214"),
    (4, "204"),
    (5, "102"),
    (6, "101"),
    (10, "162"),
    (12, "154"),
    (25, "222"),
)


def paired(*pairs: tuple[int, str | None]) -> list[dict[str, object]]:
    return [stu(sequence, stop_id, arrival={"delay": 60}) for sequence, stop_id in pairs]


def swapped(index: int, stop_id: str) -> tuple[tuple[int, str], ...]:
    """`CORRECT` with one pairing's stop_id replaced."""
    changed = list(CORRECT)
    changed[index] = (changed[index][0], stop_id)
    return tuple(changed)


def on_trip_one(tmp_path, *pairs: tuple[int, str | None]):
    updates = trip_update(*paired(*pairs), trip_id="1")
    return run(check, tmp_path, updates, tables=bullrunner())


# --- upstream's testE45 -----------------------------------------------------


def test_every_pairing_correct_reports_nothing(tmp_path):
    """Upstream, testE45: `expected.clear()`."""
    assert on_trip_one(tmp_path, *CORRECT) == []


def test_the_first_pairing_wrong_reports_once(tmp_path):
    """Upstream, testE45: stop_sequence 1 with stop_id 204, `E045, 1`."""
    assert len(on_trip_one(tmp_path, *swapped(0, "204"))) == 1


def test_the_first_two_pairings_wrong_report_twice(tmp_path):
    """Upstream, testE45: 1 with 204 and 2 with 222, `E045, 2`."""
    pairs = list(swapped(0, "204"))
    pairs[1] = (2, "222")

    assert len(on_trip_one(tmp_path, *pairs)) == 2


def test_the_first_and_third_pairings_wrong_report_twice(tmp_path):
    """Upstream, testE45: 1 and 3 both with stop_id 240, `E045, 2`."""
    pairs = list(swapped(0, "240"))
    pairs[2] = (3, "240")

    assert len(on_trip_one(tmp_path, *pairs)) == 2


def test_the_third_and_fourth_pairings_wrong_report_twice(tmp_path):
    """Upstream, testE45: 3 with 222 and 4 with 201, `E045, 2`."""
    pairs = list(swapped(2, "222"))
    pairs[3] = (4, "201")

    assert len(on_trip_one(tmp_path, *pairs)) == 2


def test_starting_at_stop_sequence_two_with_correct_pairings_reports_nothing(tmp_path):
    """Upstream, testE45: the last eight pairings only, `expected.clear()`. The
    walk skips the first GTFS row rather than failing to match."""
    assert on_trip_one(tmp_path, *CORRECT[1:]) == []


def test_starting_at_stop_sequence_two_with_stop_sequence_ten_wrong_reports_once(tmp_path):
    """Upstream, testE45: stop_sequence 10 with stop_id 160, `E045, 1`."""
    pairs = list(CORRECT[1:])
    pairs[5] = (10, "160")

    assert len(on_trip_one(tmp_path, *pairs)) == 1


def test_starting_at_stop_sequence_two_with_ten_and_twenty_five_wrong_report_twice(tmp_path):
    """Upstream, testE45: 10 with 160 and 25 with 101, `E045, 2`."""
    pairs = list(CORRECT[1:])
    pairs[5] = (10, "160")
    pairs[7] = (25, "101")

    assert len(on_trip_one(tmp_path, *pairs)) == 2


def test_stop_sequences_with_no_stop_ids_report_nothing(tmp_path):
    """Upstream, testE45: the last eight stop_sequences with stop_id cleared,
    `expected.clear()`. `hasStopId()` is the first half of the condition."""
    assert on_trip_one(tmp_path, *((sequence, None) for sequence, _ in CORRECT[1:])) == []


def test_stop_ids_with_no_stop_sequences_report_nothing(tmp_path):
    """Upstream, testE45: stop_ids only, `expected` holding just the E009 that
    `test_rule_e009.py` carries. The call site is inside the stop_sequence match,
    so a feed that sends no stop_sequences never reaches it."""
    updates = trip_update(
        *(stu(stop_id=stop_id, arrival={"delay": 60}) for _, stop_id in CORRECT), trip_id="1"
    )

    assert run(check, tmp_path, updates, tables=bullrunner()) == []


# --- the occurrence text, which upstream never looks at ---------------------


def test_the_prefix_names_both_stop_ids_and_the_stop_sequence_twice(tmp_path):
    """Ours, read off `:407-411`. The feed's stop_sequence and the GTFS one are
    always the same number here, because this is only reached on a match, and
    the space after the trip id comes from the `tripId` local ending in one."""
    assert found(on_trip_one(tmp_path, *swapped(0, "204"))) == [
        "GTFS-rt trip_id 1 stop_sequence 1 has stop_id 204 but GTFS stop_sequence 1 has stop_id 222"
    ]


def test_a_stop_id_the_static_feed_does_not_have_at_all_still_reports(tmp_path):
    """Ours. The comparison is against the matched row's stop_id, not against
    the set of known stop_ids, which is E011's question rather than this one."""
    expected = (
        "GTFS-rt trip_id 1 stop_sequence 1 has stop_id NOT_A_STOP "
        "but GTFS stop_sequence 1 has stop_id 222"
    )

    assert found(on_trip_one(tmp_path, (1, "NOT_A_STOP"))) == [expected]
