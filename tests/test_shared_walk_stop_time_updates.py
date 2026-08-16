"""The single pass twelve rules read, and the control flow only it can have.

Every assertion here is **ours**. Upstream has no test of the walk as such: its
`StopTimeUpdateValidatorTest` asserts per-rule counts out of the whole
validator, and those counts are ported into the twelve `test_rule_e0NN.py`
files. What is left over is the part of `StopTimeUpdateValidator.java:79-198`
that no single rule can observe on its own, and that a port gets wrong in the
direction of emitting more than the jar does:

1. `checkE041` is called per TripUpdate, at `:79`, rather than in a pass of its
   own. Where it sits *inside* the TripUpdate is unobservable and the section
   below says why.
2. `previousRtStopSequence` and `previousRtStopId` take the **unguarded**
   getters (`:111-112`), so they become 0 and `""` for an absent field, while
   the two accumulator lists append only under `hasStopSequence()` /
   `hasStopId()` (`:113-118`). Adjacent lines, different conditions.
3. `gtfsStopTimeIndex` never rewinds (`:119-166`), which is what makes the whole
   validator O(n + m) and what makes a gap in the feed's stop_sequences consume
   GTFS rows a later stop_time_update can then never match.
4. E051 `break`s out of the stop_time_update loop (`:180`), abandoning the rest
   of that trip for **every** rule in the validator.

The walk's other half, the shared-stream contract it owes `_shared/walks.py`,
is `test_shared_walk_stop_time_updates_stream.py`.
"""

from __future__ import annotations

from collections.abc import Iterable

from gtfs_rt_validator.rules._shared.walks import Event
from stufixtures import bullrunner, counts, ids, nine, stu, trip_update, walk


def prefixes(found: Iterable[Event], rule_id: str) -> list[str]:
    return [event.prefix for event in found if event.rule_id == rule_id]


# --- 1. checkE041 is emitted with its own entity, not batched ----------------
#
# What `:79` can and cannot be tested for. `checkE041` reports only when the
# stop_time_update list is empty (`:306`), and every other event this walk
# produces needs at least one stop_time_update, so no TripUpdate can ever emit
# E041 *and* something else. Its position **within** a TripUpdate is therefore
# not observable at all: moving the call to the end of `_trip_update` changes no
# byte of any feed, measured over both feeds below and provable from the gate.
#
# What is observable is that E041 is emitted while the walk stands on its own
# entity, rather than gathered into a pass of its own. Upstream builds fifteen
# lists and writes them grouped by rule, so batching is the port mistake to
# guard against, and it takes both feeds to catch it in both directions: the
# empty TripUpdate goes first in one and last in the other. Measured against
# mutants of the walk: a pre-pass over every entity passes the first and fails
# the second, a post-pass fails the first and passes the second.


def test_e041_is_not_gathered_into_a_pass_that_runs_after_the_others(tmp_path):
    """The empty TripUpdate is the feed's first entity, so E041 leads."""
    found = walk(tmp_path, trip_update(trip_id="1.1"), trip_update(stu(), trip_id="1.1"))

    assert ids(found) == ["E041", "E040", "E043"]


def test_e041_is_not_gathered_into_a_pass_that_runs_before_the_others(tmp_path):
    """The same two entities the other way round, which is the half that bites.

    A port that walked every entity for E041 first and then walked them again
    for everything else would produce upstream's own grouping and pass the case
    above. Here it puts E041 ahead of an earlier entity's events, where the jar
    reports it after them."""
    found = walk(tmp_path, trip_update(stu(), trip_id="1.1"), trip_update(trip_id="1.1"))

    assert ids(found) == ["E040", "E043", "E041"]


# --- 2. the unguarded getters versus the guarded appends ---------------------


def test_an_absent_stop_sequence_carries_0_forward_into_e036(tmp_path):
    """`previousRtStopSequence = stopTimeUpdate.getStopSequence()` at `:111` has
    no `hasStopSequence()` guard, so an update without one stores 0 and an
    explicit stop_sequence 0 next to it repeats that 0."""
    found = walk(
        tmp_path,
        trip_update(stu(stop_id="A", arrival={"delay": 60}), stu(0, arrival={"delay": 60})),
    )

    assert prefixes(found, "E036") == ["entity ID TEST_ENTITY has repeating stop_sequence 0"]


def test_an_absent_stop_sequence_does_not_reach_the_sortedness_list(tmp_path):
    """`:113-114` is guarded where `:111` is not. The 0 that E036 saw above is
    not in E002's list, so 0 then 1 is still strictly increasing."""
    found = walk(
        tmp_path,
        trip_update(
            stu(stop_id="A", arrival={"delay": 60}),
            stu(0, arrival={"delay": 60}),
            stu(1, arrival={"delay": 60}),
        ),
    )

    assert "E002" not in counts(found)


def test_an_absent_stop_id_carries_the_empty_string_and_e037_guards_on_it(tmp_path):
    """`:112` is unguarded too, but `checkE037` opens with
    `!previousStopId.isEmpty()`, so the empty string it stored never matches."""
    found = walk(
        tmp_path,
        trip_update(stu(1, arrival={"delay": 60}), stu(2, stop_id="", arrival={"delay": 60})),
    )

    assert "E037" not in counts(found)


# --- 3. the index that never rewinds ----------------------------------------


def test_a_gap_in_the_feeds_stop_sequences_consumes_the_gtfs_rows_it_skipped(tmp_path):
    """The walk leaves `gtfsStopTimeIndex` past row 10 once stop_sequence 10 has
    matched, so a later stop_time_update naming stop_sequence 3 can never be
    found and trips E051 rather than matching."""
    found = walk(tmp_path, trip_update(*nine(10, 3), trip_id="1"), tables=bullrunner())

    assert prefixes(found, "E051") == ["GTFS-rt trip_id 1 contains stop_sequence 3"]


def test_a_matched_stop_sequence_reaches_e046_from_one_call_site_only(tmp_path):
    """The stop-id branch at `:152` is gated on `!stu.hasStopSequence()`, so when
    the feed supplies a stop_sequence the second `checkE046` call site is dead
    and a matching stop_time_update yields at most one arrival and one departure
    event, never two of each."""
    found = walk(
        tmp_path,
        trip_update(stu(3, "214", arrival={"delay": 60}, departure={"delay": 60}), trip_id="1"),
        tables=bullrunner(timepoints=True),
    )

    assert prefixes(found, "E046") == [
        "GTFS-rt trip_id 1 stop_sequence 3 arrival.time",
        "GTFS-rt trip_id 1 stop_sequence 3 departure.time",
    ]


def test_a_stop_sequence_that_matches_nothing_reaches_e046_from_neither(tmp_path):
    """`checkE046` at `:130` sits inside `if (gtfsStopSequence == ...)`, so a
    stop_sequence no GTFS row carries walks to the end and reports E051 with no
    E046 call at all. A port that checked E046 once per stop_time_update rather
    than once per match would report one here."""
    found = walk(
        tmp_path,
        trip_update(stu(250, arrival={"delay": 60}), trip_id="1"),
        tables=bullrunner(timepoints=True),
    )

    assert counts(found) == {"E051": 1}


def test_a_trip_absent_from_stop_times_reaches_neither_e045_e046_nor_e051(tmp_path):
    """`gtfsStopTimes` stays null at `:80-86` when the TripUpdate names no
    trip_id, or names one `stop_times.txt` does not have, and the whole `while`
    loop at `:119` is then skipped."""
    unknown = walk(
        tmp_path,
        trip_update(stu(250, "214", arrival={"delay": 60}), trip_id="NOT_A_TRIP"),
        tables=bullrunner(timepoints=True),
    )
    anonymous = walk(
        tmp_path,
        trip_update(stu(250, "214", arrival={"delay": 60})),
        tables=bullrunner(timepoints=True),
    )

    assert unknown == ()
    assert anonymous == ()


def test_the_stop_id_branch_re_reads_the_row_the_index_just_left(tmp_path):
    """`:160` passes `gtfsStopTimes.get(gtfsStopTimeIndex - 1)`, because `:143`
    already incremented. The row E046 is asked about is therefore the row whose
    stop_id matched and not the one after it, and the prefix names which
    stop_time_update was being checked when it was read."""
    found = walk(
        tmp_path,
        trip_update(stu(stop_id="214", arrival={"delay": 60}), trip_id="1"),
        tables=bullrunner(timepoints=True),
    )

    assert prefixes(found, "E046") == ["GTFS-rt trip_id 1 stop_id 214 arrival.time"]


def test_reading_the_row_after_the_match_instead_would_report_nothing(tmp_path):
    """The other half of the `- 1`, from the direction that catches an off-by-one.
    Stop_id `418` is stop_sequence 18, a timepoint, so its row has times and E046
    stays quiet; the row *after* it, stop_sequence 19, is blank. A port reading
    `gtfsStopTimeIndex` rather than `gtfsStopTimeIndex - 1` reports E046 here.

    The E009 is unavoidable and not incidental to the point: matching by stop_id
    means sending no stop_sequence, and this trip visits stop_id 222 twice.
    Upstream's own stop_id-only E046 case expects the same pairing."""
    found = walk(
        tmp_path,
        trip_update(stu(stop_id="418", arrival={"delay": 60}), trip_id="1"),
        tables=bullrunner(timepoints=True),
    )

    assert counts(found) == {"E009": 1}


# --- 4. the break, which abandons the trip for every rule -------------------


def test_e051_abandons_the_rest_of_the_trip_for_every_rule_not_only_itself(tmp_path):
    """`:180`. The second stop_time_update names a stop_sequence no GTFS row has,
    so the walk stops there and the third one is never checked at all: no E040
    for its missing stop_id and stop_sequence, no E043 for its missing arrival
    and departure. A rule looping on its own would report both."""
    found = walk(
        tmp_path,
        trip_update(stu(1, arrival={"delay": 60}), stu(250), stu(), trip_id="1"),
        tables=bullrunner(),
    )

    assert counts(found) == {"E043": 1, "E051": 1}


def test_the_stop_time_update_that_trips_e051_is_itself_still_checked(tmp_path):
    """The `break` is at `:180`, *after* the four per-stop_time_update checks at
    `:168-171`, so the offending stop_time_update gets its own E043 first. Only
    what follows it is abandoned."""
    found = walk(tmp_path, trip_update(stu(250), stu(), trip_id="1"), tables=bullrunner())

    assert ids(found) == ["E043", "E051"]


def test_a_bad_stop_sequence_at_the_start_of_a_trip_reports_at_the_last_gtfs_row(tmp_path):
    """The flag at `:148-151` is only ever set when the index reaches the end of
    `stop_times.txt`, so a stop_sequence 0 in the first stop_time_update consumes
    all 25 rows before anything is reported. The stop_sequence in the text is the
    offending one, and the eight stop_time_updates after it are gone."""
    found = walk(
        tmp_path,
        trip_update(*nine(0, 2, 3, 4, 5, 6, 10, 12, 25), trip_id="1"),
        tables=bullrunner(),
    )

    assert counts(found) == {"E051": 1}
    assert prefixes(found, "E051") == ["GTFS-rt trip_id 1 contains stop_sequence 0"]


def test_the_break_ends_one_trip_and_not_the_feed(tmp_path):
    """`unknownRtStopSequence` is declared inside the entity loop (`:97`), so the
    next TripUpdate starts clean and its bare stop_time_update is checked in
    full. `foundE009error` is declared on the same lines and resets too, which
    is why the second entity reports E009 for a trip_id the first also named."""
    found = walk(
        tmp_path,
        trip_update(stu(250), trip_id="1"),
        trip_update(stu(), trip_id="1"),
        tables=bullrunner(),
    )

    assert ids(found) == ["E043", "E051", "E009", "E040", "E043"]


def test_e002_reads_the_truncated_list_the_break_left_behind(tmp_path):
    """`:184` runs on whatever reached `rtStopSequenceList` before the break, so
    an out-of-order stop_sequence sitting after the offending one is never
    weighed. Without the break this feed is unsorted and reports E002."""
    found = walk(tmp_path, trip_update(*nine(1, 2, 250, 3), trip_id="1"), tables=bullrunner())

    assert counts(found) == {"E051": 1}
