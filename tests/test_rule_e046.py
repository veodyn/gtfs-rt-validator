"""E046, against upstream's own `testE46`.

Every assertion marked "upstream" is transcribed from the real
`StopTimeUpdateValidatorTest.java` (`testE46`, `:2041-2419`), not from the
reference's summary of it. Upstream asserts counts and nothing else, so every
assertion about occurrence text is ours.

The feed is `bullrunner-gtfs-timepoints-only-legacy-exact-times-1.zip` trip `1`,
whose `stop_times.txt` keeps `arrival_time` and `departure_time` only at
stop_sequences 1, 7, 13, 18, 22 and 25 and leaves every other row blank.

**The reference is wrong about this rule and the correction is tested below.**
It reads E046 as "the producer sent only a delay". Neither condition at `:428`
or `:434` mentions `hasDelay()`: what they ask is whether the realtime event has
no *time* and the static row has none either. An event carrying nothing at all
therefore reports here as well as at E044.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.upstream.e046 import check
from stufixtures import bullrunner, found, run, stu, trip_update

#: `TimestampUtils.MIN_POSIX_TIME`, upstream's stand-in for a real time.
MIN_POSIX_TIME = 1104537600

#: The six timepoints of the archive, paired with their stop_ids.
TIMEPOINTS = ((1, "222"), (7, "108"), (13, "150"), (25, "222"))

#: The same four with stop_sequences 3 and 10 inserted, which are not timepoints.
WITH_BLANKS = ((1, "222"), (3, "214"), (7, "108"), (10, "162"), (13, "150"), (25, "222"))


def both(pairs, *, times: bool = False, delays: bool = True, field: str = "both"):
    """Upstream's stop_time_updates: an arrival and a departure on each."""
    updates = []
    for offset, (sequence, stop_id) in enumerate(pairs):
        event: dict[str, object] = {}
        if times:
            event["time"] = MIN_POSIX_TIME + offset
        if delays:
            event["delay"] = 60
        updates.append(stu(sequence, stop_id, arrival=dict(event), departure=dict(event)))
    return updates


def on_timepoints(tmp_path, updates):
    return run(
        check, tmp_path, trip_update(*updates, trip_id="1"), tables=bullrunner(timepoints=True)
    )


# --- upstream's testE46 -----------------------------------------------------


def test_times_on_every_stop_time_update_report_nothing(tmp_path):
    """Upstream, testE46: times only, `expected.clear()`. The realtime time is
    what satisfies the first half of each condition."""
    pairs = ((1, "222"), (2, "230"), (3, "214"), (4, "204"), (5, "102"), (6, "101"))

    assert on_timepoints(tmp_path, both(pairs, times=True, delays=False)) == []


def test_times_and_delays_on_every_stop_time_update_report_nothing(tmp_path):
    """Upstream, testE46: both fields set, `expected.clear()`."""
    pairs = ((1, "222"), (2, "230"), (3, "214"), (4, "204"), (5, "102"), (6, "101"))

    assert on_timepoints(tmp_path, both(pairs, times=True, delays=True)) == []


def test_delays_at_timepoints_only_report_nothing(tmp_path):
    """Upstream, testE46: delays at stop_sequences 1, 7, 13 and 25,
    `expected.clear()`. Every one of those GTFS rows has a time to apply the
    delay to."""
    assert on_timepoints(tmp_path, both(TIMEPOINTS)) == []


def test_delays_at_two_non_timepoints_report_four_times(tmp_path):
    """Upstream, testE46: stop_sequences 3 and 10 added, `expected.put(E046, 4)`,
    two for each: one arrival and one departure."""
    assert len(on_timepoints(tmp_path, both(WITH_BLANKS))) == 4


def test_the_same_by_stop_id_alone_still_reports_four_times(tmp_path):
    """Upstream, testE46: stop_sequence cleared, `expected.put(E046, 4)` next to
    the `E009, 1` that `test_rule_e009.py` carries. This is the second call site,
    the one that reads `gtfsStopTimeIndex - 1`."""
    updates = [
        stu(stop_id=stop_id, arrival={"delay": 60}, departure={"delay": 60})
        for _, stop_id in WITH_BLANKS
    ]

    assert len(on_timepoints(tmp_path, updates)) == 4


def test_the_same_by_stop_sequence_alone_still_reports_four_times(tmp_path):
    """Upstream, testE46: stop_id cleared, `expected.put(E046, 4)`."""
    updates = [
        stu(sequence, arrival={"delay": 60}, departure={"delay": 60}) for sequence, _ in WITH_BLANKS
    ]

    assert len(on_timepoints(tmp_path, updates)) == 4


# --- the occurrence text and the condition, which upstream never checks -----


def test_the_prefix_names_the_trip_the_stop_time_update_and_which_half(tmp_path):
    """Ours, read off `:426-437`. Two occurrences from one stop_time_update,
    arrival first, and `getStopTimeUpdateId` prefers the stop_sequence."""
    updates = [stu(3, "214", arrival={"delay": 60}, departure={"delay": 60})]

    assert found(on_timepoints(tmp_path, updates)) == [
        "GTFS-rt trip_id 1 stop_sequence 3 arrival.time",
        "GTFS-rt trip_id 1 stop_sequence 3 departure.time",
    ]


def test_a_stop_id_only_stop_time_update_is_named_by_its_stop_id(tmp_path):
    """Ours, and the other call site's text. The E009 that comes with sending no
    stop_sequence belongs to that rule's file, so this one sees only E046."""
    updates = [stu(stop_id="214", arrival={"delay": 60})]

    assert found(on_timepoints(tmp_path, updates)) == ["GTFS-rt trip_id 1 stop_id 214 arrival.time"]


def test_an_event_with_neither_time_nor_delay_reports_too(tmp_path):
    """Ours, and the correction to that reading. `:428` and `:434` test
    `hasTime()` alone, so an empty `StopTimeEvent` over a blank GTFS cell is
    reported here as well as at E044. A port that wrote a `hasDelay()` guard
    into the condition would report nothing."""
    updates = [stu(3, "214", arrival={})]

    assert found(on_timepoints(tmp_path, updates)) == [
        "GTFS-rt trip_id 1 stop_sequence 3 arrival.time"
    ]


def test_a_stop_time_update_with_no_arrival_or_departure_reports_nothing(tmp_path):
    """Ours. Both conditions open on `hasArrival()` / `hasDeparture()`, so a
    stop_time_update predicting nothing is E043's business, not this rule's."""
    assert on_timepoints(tmp_path, [stu(3, "214")]) == []


def test_a_stop_sequence_that_matches_no_gtfs_row_reports_nothing(tmp_path):
    """Ours, and the correction the coordinator's audit turned up: `checkE046`
    at `:130` sits inside the stop_sequence match, so an unmatched stop_sequence
    walks to the end of `stop_times.txt` and reaches E051 with no E046 call at
    all. A port that checked once per stop_time_update would report here."""
    assert on_timepoints(tmp_path, [stu(250, arrival={"delay": 60})]) == []


def test_a_trip_absent_from_stop_times_reports_nothing(tmp_path):
    """Ours. `gtfsStopTimes` stays null (`:80-86`) and the whole `while` loop is
    skipped, so there is no static row to ask about however blank the feed is."""
    updates = trip_update(stu(3, "214", arrival={"delay": 60}), trip_id="NOT_A_TRIP")

    assert run(check, tmp_path, updates, tables=bullrunner(timepoints=True)) == []


def test_a_static_feed_with_times_everywhere_reports_nothing(tmp_path):
    """Ours, the control. The same stop_time_updates against the ordinary
    `bullrunner-gtfs.zip`, where no row is blank."""
    updates = trip_update(*both(WITH_BLANKS), trip_id="1")

    assert run(check, tmp_path, updates, tables=bullrunner()) == []
