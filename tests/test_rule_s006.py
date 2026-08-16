"""S006: an update giving one time where `stop_times.txt` gives two.

**The band is disjoint from E043's and the disjointness is the design.** E043
reports an update with *neither* arrival nor departure; this one reports an
update with exactly one where the schedule has both. No feed can be in both
bands at once, and the test at the end of this module is what says so, rather
than the one-line E043 entry `tests/test_tier_overlap.py` keeps in `OVERLAP`.

The clause sits inside the `SCHEDULED` member's own comment block, and the two
other members relax the same requirement in their own words: SKIPPED says
"Arrival and departure are optional" (`:246`) and NO_DATA says "Neither arrival
nor departure should be supplied" (`:250`). So the rule is scoped to SCHEDULED
updates, which is the narrow reading and the one that cannot over-fire.

**The second half of the module is the terminal-stop narrowing**, which came
out of a real agency's feed rather than out of the sentence. Its tests come in
pairs on purpose: for each end of the trip, the event that end does not have and
the event it still owes. The exemption is only worth having if the second half
of each pair keeps failing when it should.

The tables live in `s006fixtures.py`, split out at the file cap. Four shapes of
`stop_times.txt` matter here and naming them is what keeps a test readable.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.spec.s006 import check
from gtfs_rt_validator.rules.upstream.e043 import check as e043
from s006fixtures import (
    loop_tables,
    run,
    run_over,
    solo_tables,
    tables,
    trip_update,
    update,
)
from specfixtures import entity, feed_context, message, minimal, prefixes


def test_both_times_given_is_what_the_clause_asks_for(tmp_path):
    found = run(
        tmp_path,
        entity(
            trip_update=trip_update(
                update(stop_id="S1", arrival={"time": 1}, departure={"time": 2})
            )
        ),
    )

    assert prefixes(found) == []


def test_only_an_arrival_where_the_schedule_has_both_is_reported(tmp_path):
    found = run(
        tmp_path, entity(trip_update=trip_update(update(stop_id="S1", arrival={"time": 1})))
    )

    assert prefixes(found) == [
        "trip_id T1 stop_id S1 gives only arrival where stop_times.txt gives both times"
    ]


def test_only_a_departure_where_the_schedule_has_both_is_reported(tmp_path):
    found = run(
        tmp_path, entity(trip_update=trip_update(update(stop_id="S2", departure={"time": 1})))
    )

    assert prefixes(found) == [
        "trip_id T1 stop_id S2 gives only departure where stop_times.txt gives both times"
    ]


def test_a_stop_whose_schedule_has_one_time_is_not_in_the_clauses_antecedent(tmp_path):
    """ "If the schedule for this stop contains both arrival and departure
    times", and S3's does not."""
    found = run(
        tmp_path, entity(trip_update=trip_update(update(stop_id="S3", departure={"time": 1})))
    )

    assert prefixes(found) == []


def test_the_stop_is_matched_by_stop_sequence_when_the_update_gives_one(tmp_path):
    found = run(
        tmp_path,
        entity(trip_update=trip_update(update(stop_sequence=1, arrival={"time": 1}))),
    )

    assert prefixes(found) == [
        "trip_id T1 stop_sequence 1 gives only arrival where stop_times.txt gives both times"
    ]


def test_a_stop_sequence_no_row_carries_is_e051s_business(tmp_path):
    found = run(
        tmp_path,
        entity(trip_update=trip_update(update(stop_sequence=99, arrival={"time": 1}))),
    )

    assert prefixes(found) == []


def test_a_trip_absent_from_stop_times_txt_is_e003s_business(tmp_path):
    found = run(
        tmp_path,
        entity(trip_update=trip_update(update(stop_id="S1", arrival={"time": 1}), trip_id="NOPE")),
    )

    assert prefixes(found) == []


def test_a_trip_update_with_no_trip_id_names_no_schedule(tmp_path):
    found = run(
        tmp_path,
        entity(
            trip_update={
                "trip": {"route_id": "R1"},
                "stop_time_update": [update(stop_id="S1", arrival={"time": 1})],
            }
        ),
    )

    assert prefixes(found) == []


def test_a_skipped_update_is_exempt(tmp_path):
    """`:246`: "Arrival and departure are optional"."""
    found = run(
        tmp_path,
        entity(trip_update=trip_update(update("SKIPPED", stop_id="S1", arrival={"time": 1}))),
    )

    assert prefixes(found) == []


def test_a_no_data_update_is_exempt(tmp_path):
    """`:250`: "Neither arrival nor departure should be supplied"."""
    found = run(
        tmp_path,
        entity(trip_update=trip_update(update("NO_DATA", stop_id="S1", arrival={"time": 1}))),
    )

    assert prefixes(found) == []


def test_the_occurrence_locates_the_update_and_carries_this_rules_id(tmp_path):
    found = run(
        tmp_path, entity(trip_update=trip_update(update(stop_id="S1", arrival={"time": 1})))
    )

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.stop_time_update[0]"
    ]
    assert [occurrence.rule_id for occurrence in found] == ["S006"]


# --- the terminal stops, which are the shape a real agency showed ------------
#
# Measured over six MBTA messages: of every one-sided SCHEDULED update in the
# recording, 473 were the trip's own first stop with a departure only and 652
# its own last stop with an arrival only. None was in the middle. A trip's
# first stop has no arrival to predict and its last stop has no departure, and
# `stop_times.txt` fills both columns anyway because GTFS wants both or
# neither, so the schedule cannot tell the two apart and the rule was reporting
# a producer doing the right thing.


def test_the_first_stop_of_the_trip_owes_no_arrival(tmp_path):
    """S1 is `tables()`'s first row. There is no arrival to predict there."""
    found = run(
        tmp_path, entity(trip_update=trip_update(update(stop_id="S1", departure={"time": 2})))
    )

    assert prefixes(found) == []


def test_the_first_stop_still_owes_its_departure(tmp_path):
    """The other half of the asymmetry. Only the *arrival* is excused at a first
    stop, so an update giving the arrival and withholding the departure is the
    genuine defect the exemption must not swallow."""
    found = run(
        tmp_path, entity(trip_update=trip_update(update(stop_id="S1", arrival={"time": 1})))
    )

    assert prefixes(found) == [
        "trip_id T1 stop_id S1 gives only arrival where stop_times.txt gives both times"
    ]


def test_the_last_stop_of_the_trip_owes_no_departure(tmp_path):
    """`minimal()` alone stops T1 at S2, so S2 is the last row and both of its
    times are in the clause's antecedent."""
    found = run_over(
        tmp_path,
        minimal(),
        entity(trip_update=trip_update(update(stop_id="S2", arrival={"time": 1}))),
    )

    assert prefixes(found) == []


def test_the_last_stop_still_owes_its_arrival(tmp_path):
    found = run_over(
        tmp_path,
        minimal(),
        entity(trip_update=trip_update(update(stop_id="S2", departure={"time": 2}))),
    )

    assert prefixes(found) == [
        "trip_id T1 stop_id S2 gives only departure where stop_times.txt gives both times"
    ]


def test_a_stop_in_the_middle_owes_both(tmp_path):
    """S2 is neither end of `tables()`, so neither excuse reaches it."""
    found = run(
        tmp_path, entity(trip_update=trip_update(update(stop_id="S2", arrival={"time": 1})))
    )

    assert prefixes(found) == [
        "trip_id T1 stop_id S2 gives only arrival where stop_times.txt gives both times"
    ]


def test_a_one_stop_trip_is_its_own_first_and_last_stop(tmp_path):
    """Both excuses apply at once, so either one-sided update is silent. A trip
    with one stop has no journey between stops for either event to be about."""
    entities = (
        entity(trip_update=trip_update(update(stop_id="S1", arrival={"time": 1}), trip_id="T2")),
        entity(trip_update=trip_update(update(stop_id="S1", departure={"time": 2}), trip_id="T2")),
    )

    assert prefixes(run_over(tmp_path, solo_tables(), *entities)) == []


def test_a_repeated_stop_id_leaves_the_position_undecidable(tmp_path):
    """T1 now visits S1 twice, so `stop_id` alone does not say which visit this
    update is about and therefore does not say whether it is at a terminal.
    Silence is the deliberate answer: the excuse cannot be ruled in or out."""
    found = run_over(
        tmp_path,
        loop_tables(),
        entity(trip_update=trip_update(update(stop_id="S1", arrival={"time": 1}))),
    )

    assert prefixes(found) == []


def test_a_stop_sequence_decides_the_position_a_repeated_stop_id_cannot(tmp_path):
    """The same loop trip, named the way `:95` of the Best Practices asks for.
    S2 is the middle row, so the report the test above withholds is made here."""
    found = run_over(
        tmp_path,
        loop_tables(),
        entity(trip_update=trip_update(update(stop_sequence=2, arrival={"time": 1}))),
    )

    assert prefixes(found) == [
        "trip_id T1 stop_sequence 2 gives only arrival where stop_times.txt gives both times"
    ]


# --- the band, against E043, the rule this one declares as its border --------


def test_neither_event_is_e043s_band_and_not_this_rules(tmp_path):
    """The disjointness, asserted rather than claimed. E043 fires and S006 does
    not; the reverse holds in the test below."""
    feed = message(entity(trip_update=trip_update(update(stop_id="S1"))))

    assert prefixes(check(feed, feed_context(tmp_path, tables()))) == []
    assert len(list(e043(feed, feed_context(tmp_path, tables())))) == 1


def test_exactly_one_event_is_this_rules_band_and_not_e043s(tmp_path):
    feed = message(entity(trip_update=trip_update(update(stop_id="S1", arrival={"time": 1}))))

    assert len(list(check(feed, feed_context(tmp_path, tables())))) == 1
    assert list(e043(feed, feed_context(tmp_path, tables()))) == []
