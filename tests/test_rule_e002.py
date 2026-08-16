"""E002, against upstream's `testE002` and `testE002noStopSequenceGtfsRt`.

Every assertion marked "upstream" is transcribed from the real
`StopTimeUpdateValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testE002`, `:45-121`; `testE002noStopSequenceGtfsRt`, `:129-401`), not from
a second-hand summary of it. Upstream asserts counts and nothing else, so
every assertion about occurrence text below is ours.

`testE002` runs against `testagency.zip` with **no trip_id set at all**, so
`gtfsStopTimes` is null and the walk's static half never engages: those cases
are purely about the list the feed supplied. `testE002noStopSequenceGtfsRt`
runs against `bullrunner-gtfs.zip` trip `1` with stop_ids only, which is the
other form of the rule, and every one of its cases also reports the E009 that
trip's repeated stop_id earns.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.upstream.e002 import check
from stufixtures import bullrunner, found, nine, run, stu, trip_update

#: The nine stop_ids upstream sends, in `stop_times.txt` order.
IN_ORDER = ("222", "230", "214", "204", "102", "101", "162", "154", "222")


def by_stop_id(*stop_ids: str) -> list[dict[str, object]]:
    """Upstream's stop_id-only stop_time_updates, each with an arrival delay."""
    return [stu(stop_id=stop_id, arrival={"delay": 60}) for stop_id in stop_ids]


def on_bullrunner(tmp_path, *updates):
    return run(check, tmp_path, trip_update(*updates, trip_id="1"), tables=bullrunner())


# --- upstream's testE002: stop_sequences the feed supplied ------------------


def test_ordered_stop_sequences_report_nothing(tmp_path):
    """Upstream, testE002: stop_sequences 1, 5, `expected.clear()`."""
    assert run(check, tmp_path, trip_update(*nine(1, 5))) == []


def test_an_out_of_order_stop_sequence_reports_once(tmp_path):
    """Upstream, testE002: 1, 5, 3, `expected.put(E002, 1)`."""
    assert len(run(check, tmp_path, trip_update(*nine(1, 5, 3)))) == 1


def test_a_repeated_stop_sequence_is_unsorted_too(tmp_path):
    """Upstream, testE002: 1, 3, 3, 5, `expected.put(E002, 1)` alongside the
    `expected.put(E036, 1)` that `test_rule_e036.py` carries. Guava's
    `isStrictlyOrdered` is strictly increasing, so equal is out of order."""
    assert len(run(check, tmp_path, trip_update(*nine(1, 3, 3, 5)))) == 1


def test_the_first_form_names_the_stop_sequences_it_saw(tmp_path):
    """Ours, read off `:188`. Java's `List.toString()`, which is square brackets
    with a comma and a space, not Python's `str(list)`. No trip_id is set, which
    is upstream's own fixture, so the prefix falls back to the entity id."""
    assert found(run(check, tmp_path, trip_update(*nine(1, 5, 3)))) == [
        "entity ID TEST_ENTITY stop_sequence [1, 5, 3]"
    ]


def test_a_single_stop_sequence_and_an_empty_trip_are_both_sorted(tmp_path):
    """Ours. `isStrictlyOrdered` over nought or one element is vacuously true,
    and a TripUpdate with no stop_time_updates reaches E002 with an empty list
    after E041 has already reported it."""
    assert run(check, tmp_path, trip_update(*nine(7))) == []
    assert run(check, tmp_path, trip_update()) == []


def test_only_the_stop_sequences_that_were_present_are_weighed(tmp_path):
    """Ours, and the guarded-append half of `:113-118`. The middle
    stop_time_update has no stop_sequence, so nothing of it reaches the list and
    1 then 2 is still increasing, even though `previousRtStopSequence` saw a 0."""
    assert run(check, tmp_path, trip_update(*nine(1), stu(stop_id="A"), *nine(2))) == []


# --- upstream's testE002noStopSequenceGtfsRt: stop_ids only -----------------


def test_stop_ids_in_gtfs_order_report_nothing(tmp_path):
    """Upstream: the nine stop_ids in `stop_times.txt` order, `expected` holding
    only E009. Every one is recovered from GTFS by stop_id, so the list is nine
    long and increasing."""
    assert on_bullrunner(tmp_path, *by_stop_id(*IN_ORDER)) == []


def test_the_first_two_stop_ids_swapped_report_once(tmp_path):
    """Upstream: 230 before 222, `expected.put(E002, 1)`."""
    assert len(on_bullrunner(tmp_path, *by_stop_id("230", *IN_ORDER[:1], *IN_ORDER[2:]))) == 1


def test_a_stop_id_repeated_back_to_back_reports_once(tmp_path):
    """Upstream: 230 twice, `expected.put(E002, 1)` alongside E037 and E009."""
    assert len(on_bullrunner(tmp_path, *by_stop_id("222", "230", "230", *IN_ORDER[2:]))) == 1


def test_a_stop_id_moved_to_the_end_reports_once(tmp_path):
    """Upstream: 154 after the second 222, `expected.put(E002, 1)`."""
    assert len(on_bullrunner(tmp_path, *by_stop_id(*IN_ORDER[:7], "222", "154"))) == 1


def test_the_second_form_names_the_stop_ids_rather_than_the_stop_sequences(tmp_path):
    """Ours, read off `:196`. The second form fires when the walk recovered
    fewer stop_sequences from GTFS than there were stop_time_updates, which is
    what "we didn't find all of them" means, and it prints `rtStopIdList`."""
    found_text = found(on_bullrunner(tmp_path, *by_stop_id("230", *IN_ORDER[:1], *IN_ORDER[2:])))

    assert found_text == [
        "trip_id 1 stop_sequence for stop_ids [230, 222, 214, 204, 102, 101, 162, 154, 222]"
    ]


def test_the_two_forms_are_mutually_exclusive(tmp_path):
    """Ours. `:189` is an `else if`, so a feed that is both unsorted and short of
    recovered stop_sequences reports the first form once and never both."""
    updates = [stu(5, arrival={"delay": 60}), *by_stop_id("214"), stu(1, arrival={"delay": 60})]

    assert found(run(check, tmp_path, trip_update(*updates))) == [
        "entity ID TEST_ENTITY stop_sequence [5, 1]"
    ]
